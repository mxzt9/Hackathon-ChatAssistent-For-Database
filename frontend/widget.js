(async function () {
    'use strict';
    const chatId = new URLSearchParams(location.search).get('chat') || (location.pathname.startsWith('/chat/') ? location.pathname.slice(6) : null);
    const chatPath = chatId ? '/api/chats/' + encodeURIComponent(chatId) : '/api/database';
    const queryPath = chatId ? '/api/chats/' + encodeURIComponent(chatId) + '/query' :
        '/api/query';
    const form = document.getElementById('widget-form');
    const input = document.getElementById('widget-input');
    const log = document.getElementById('widget-messages');
    const status = document.getElementById('widget-status');
    const send = document.getElementById('send-question');
    const cancel = document.getElementById('cancel-question');
    const messages = [];
    let busy = false,
        controller, generation = 0;

    function render() {
        log.innerHTML = messages.map(message =>
            `<article class="message ${message.role}">${message.role === 'assistant' ? '<span class="message-author">Ассистент</span>' : ''}<div class="message-body">${ChatUI.content(message)}</div></article>`
        ).join('') + (busy ?
            '<p class="typing" role="status">Выполняется запрос…</p>' : '');
        send.disabled = busy;
        input.disabled = busy;
        cancel.hidden = !busy;
        log.scrollTop = log.scrollHeight;
    }
    async function query(question) {
        if (busy) return;
        busy = true;
        controller = new AbortController();
        const current = ++generation;
        messages.push({
            role: 'user',
            text: question
        });
        render();
        status.textContent = 'Ассистент проверяет данные…';
        try {
            const response = await fetch(queryPath, {
                method: 'POST',
                credentials: 'omit',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    question
                }),
                signal: controller.signal
            });
            const result = await response.json();
            if (current !== generation) return;
            if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Не удалось выполнить запрос.');
            messages.push({
                role: 'assistant',
                text: result.error || result.answer,
                sql: result.sql,
                table: result.error ? null : {
                    fields: result.columns,
                    rows: result.rows
                },
                meta: result.meta
            });
            status.textContent = result.error ? 'Запрос не выполнен.' :
                'Ответ получен из базы данных.';
        } catch (error) {
            if (current !== generation) return;
            if (error.name === 'AbortError') status.textContent = 'Запрос отменён.';
            else {
                messages.push({
                    role: 'assistant',
                    text: error.message
                });
                status.textContent = 'Запрос не выполнен.';
            }
        } finally {
            if (current === generation) {
                busy = false;
                messages.splice(0, Math.max(0, messages.length - 60));
                render();
                input.focus();
            }
        }
    }
    form.addEventListener('submit', (event) => {
        event.preventDefault();
        const text = input.value.trim();
        if (text) {
            input.value = '';
            query(text);
        }
    });
    document.querySelectorAll('[data-question]').forEach(button => {
        button.addEventListener('click', () => {
            if (busy) return;
            input.value = button.dataset.question;
            form.requestSubmit();
        });
    });
    input.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
            event.preventDefault();
            form.requestSubmit();
        }
    });
    cancel.addEventListener('click', () => {
        controller?.abort();
    });
    document.getElementById('clear-chat').addEventListener('click', () => {
        if (busy) controller?.abort();
        ++generation;
        busy = false;
        messages.length = 0;
        render();
        status.textContent = 'История очищена.';
    });
    async function initializeChat() {
        try {
            const response = await fetch(chatPath, {
                credentials: 'omit'
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail);
            document.getElementById('chat-title').textContent = data.name;
            if (data.sql_backend === 'local') status.textContent =
                'Демонстрационный генератор SQL · выберите пример или задайте похожий вопрос';
            if (!messages.length) messages.push({
                role: 'assistant',
                text: data.configured ?
                    'Задайте вопрос о данных. Я покажу ответ, SQL и таблицу результатов.' : 'Сначала включите таблицы в настройках доступа.'
            });
            render();
            document.getElementById('retry-database').hidden = true;
        } catch (error) {
            messages.push({
                role: 'assistant',
                text: error.message
            });
            render();
            send.disabled = true;
            input.disabled = true;
            document.getElementById('retry-database').hidden = false;
        }
    }
    document.getElementById('retry-database').onclick = initializeChat;
    await initializeChat();
})();
