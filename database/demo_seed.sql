-- Только синтетические данные для новой локальной БД Docker.
INSERT INTO faculties (id, name) VALUES (1, 'Факультет экономики'), (2, 'Факультет информационных технологий');
INSERT INTO programs (id, faculty_id, name) VALUES (1, 1, 'Экономика'), (2, 2, 'Информатика');
INSERT INTO teachers (id, full_name) VALUES (1, 'Преподаватель математики');
INSERT INTO courses (id, teacher_id, name) VALUES (1, 1, 'Математика');
INSERT INTO students (id, program_id, admission_year, full_name, birth_date, email, phone, passport_series, passport_number)
SELECT number, 1 + (number % 2), 2022 + (number % 5), 'Тестовый студент ' || number,
       DATE '2005-01-01', 'student' || number || '@example.invalid', 'TEST-' || number, 'TEST', number::text
FROM generate_series(1, 30) AS number;
INSERT INTO applications (id, program_id, year, status, applicant_full_name, applicant_email, applicant_phone, applicant_passport_series, applicant_passport_number)
SELECT number, 1 + (number % 2), 2026, 'accepted', 'Тестовый абитуриент ' || number,
       'applicant' || number || '@example.invalid', 'TEST-' || number, 'TEST', number::text
FROM generate_series(1, 20) AS number;
INSERT INTO grades (student_id, course_id, grade, semester)
SELECT id, 1, 2 + (id % 4), 1 FROM students;
SELECT setval(pg_get_serial_sequence('faculties', 'id'), (SELECT MAX(id) FROM faculties));
SELECT setval(pg_get_serial_sequence('programs', 'id'), (SELECT MAX(id) FROM programs));
SELECT setval(pg_get_serial_sequence('teachers', 'id'), (SELECT MAX(id) FROM teachers));
SELECT setval(pg_get_serial_sequence('courses', 'id'), (SELECT MAX(id) FROM courses));
SELECT setval(pg_get_serial_sequence('students', 'id'), (SELECT MAX(id) FROM students));
SELECT setval(pg_get_serial_sequence('applications', 'id'), (SELECT MAX(id) FROM applications));
