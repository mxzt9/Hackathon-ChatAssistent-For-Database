-- Read-only пользователь для ассистента (README BE-2, BE-7; презентация, слайд 5).
-- Последний уровень защиты: даже если guard что-то пропустит, БД не даст
-- изменить данные или прочитать закрытые колонки.
-- Выполнять от владельца БД. Пароль задать через .env, не коммитить.

CREATE ROLE assistant_ro LOGIN PASSWORD 'change_me' CONNECTION LIMIT 50;

-- Таймауты и read-only на уровне роли (дублируют настройки пула)
ALTER ROLE assistant_ro SET default_transaction_read_only = on;
ALTER ROLE assistant_ro SET statement_timeout = '3000ms';
ALTER ROLE assistant_ro SET work_mem = '4MB';
ALTER ROLE assistant_ro SET temp_file_limit = '64MB';
ALTER ROLE assistant_ro SET lock_timeout = '1000ms';
ALTER ROLE assistant_ro SET idle_in_transaction_session_timeout = '5000ms';

REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO assistant_ro;

-- Права только на колонки из whitelist.json (column-level GRANT)
GRANT SELECT ON faculties, programs, courses TO assistant_ro;
GRANT SELECT (id, full_name)
    ON teachers TO assistant_ro;

GRANT SELECT (id, program_id, admission_year)
    ON students TO assistant_ro;

GRANT SELECT (id, program_id, year, status)
    ON applications TO assistant_ro;

GRANT SELECT (id, student_id, course_id, grade, semester)
    ON grades TO assistant_ro;
