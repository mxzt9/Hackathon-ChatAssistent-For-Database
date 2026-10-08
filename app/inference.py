"""Qwen в отдельном процессе: сбой CUDA не завершает HTTP-сервер."""

import asyncio
import logging
import multiprocessing
from time import monotonic

from fastapi import HTTPException

from app.logging_config import configure_logging

LOGGER = logging.getLogger(__name__)
MAX_PENDING = 5
LOAD_TIMEOUT = 600
QUERY_TIMEOUT = 120


def model_process(connection, settings):
    # Отдельный файл исключает одновременную ротацию из двух процессов.
    configure_logging("model.log")
    try:
        import torch

        from ml.qwen import QwenSqlModel

        torch.set_num_threads(settings.torch_threads)
        LOGGER.info(
            "Загрузка модели: %s, устройство: %s", settings.model_id, settings.device
        )
        model = QwenSqlModel(settings.model_id, settings.device)
        LOGGER.info("Модель загружена, устройство: %s", model.device)
        connection.send({"ready": True})
        while True:
            payload = connection.recv()
            if payload is None:
                break
            try:
                connection.send(
                    {"sql": model.generate(payload["schema"], payload["question"])}
                )
            except (ValueError, RuntimeError) as error:
                LOGGER.warning(
                    "Ошибка генерации SQL: %s: %s",
                    type(error).__name__,
                    str(error).replace("\n", " ")[:300],
                )
                connection.send(
                    {"error": "Модель не смогла составить SQL. Уточните вопрос."}
                )
    except Exception:
        LOGGER.exception("Не удалось загрузить или выполнить Qwen")
    finally:
        connection.close()


class InferenceWorker:
    def __init__(self, settings, target=model_process):
        self.settings = settings
        self.target = target
        self.status = "not_loaded"
        self.process = self.connection = None
        self.lock = asyncio.Lock()
        self.pending = 0

    async def receive(self, timeout):
        deadline = monotonic() + timeout
        while monotonic() < deadline:
            if await asyncio.to_thread(self.connection.poll, 0.25):
                return self.connection.recv()
            if not self.process.is_alive():
                raise EOFError(f"Qwen process exited: {self.process.exitcode}")
        raise TimeoutError("Qwen exceeded time limit")

    async def warmup(self):
        async with self.lock:
            self.status = "loading"
            context = multiprocessing.get_context("spawn")
            parent, child = context.Pipe()
            self.connection = parent
            self.process = context.Process(
                target=self.target, args=(child, self.settings), daemon=True
            )
            try:
                self.process.start()
                child.close()
                payload = await self.receive(LOAD_TIMEOUT)
                if not payload.get("ready"):
                    raise RuntimeError("Qwen did not become ready")
                self.status = "ready"
                LOGGER.info("Процесс Qwen готов")
            except asyncio.CancelledError:
                LOGGER.info("Загрузка Qwen отменена при остановке сервера")
                await self.stop()
                raise
            except Exception:
                LOGGER.exception("Qwen недоступен; HTTP-сервер продолжает работать")
                await self.stop()
                self.status = "unavailable"
            finally:
                child.close()

    async def generate(self, schema, question):
        if self.status != "ready":
            raise HTTPException(
                503, "Qwen не загружен или остановлен. Проверьте журнал сервера."
            )
        # Один активный вопрос и максимум четыре ожидающих; счётчик изменяется
        # без await, поэтому два запроса не могут одновременно занять последнее место.
        if self.pending >= MAX_PENDING:
            LOGGER.warning("Запрос отклонён: очередь Qwen заполнена")
            raise HTTPException(
                503,
                "Модель занята. Повторите вопрос позже.",
                headers={"Retry-After": "5"},
            )
        self.pending += 1
        try:
            async with self.lock:
                if self.status != "ready":
                    raise HTTPException(503, "Qwen остановлен. Перезапустите сервер.")
                try:
                    self.connection.send({"schema": schema, "question": question})
                    payload = await self.receive(QUERY_TIMEOUT)
                except (EOFError, OSError, TimeoutError):
                    LOGGER.exception("Процесс Qwen остановлен")
                    await self.stop()
                    self.status = "unavailable"
                    raise HTTPException(
                        503,
                        "Qwen остановлен из-за ошибки или таймаута. HTTP-сервер работает.",
                    ) from None
                except asyncio.CancelledError:
                    await self.stop()
                    self.status = "unavailable"
                    raise
                if payload.get("error"):
                    raise HTTPException(422, payload["error"])
                return payload["sql"]
        finally:
            self.pending -= 1

    async def stop(self):
        process, connection = self.process, self.connection
        self.process = self.connection = None
        if process is not None:
            if process.is_alive():
                process.terminate()
            if process.pid is not None:
                await asyncio.to_thread(process.join, 2)
                if process.is_alive():
                    process.kill()
                    await asyncio.to_thread(process.join, 2)
            process.close()
        if connection is not None:
            connection.close()
        self.status = "not_loaded"
