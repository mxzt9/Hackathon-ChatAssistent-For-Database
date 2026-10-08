DROP TABLE IF EXISTS grades CASCADE;
DROP TABLE IF EXISTS courses CASCADE;
DROP TABLE IF EXISTS teachers CASCADE;
DROP TABLE IF EXISTS applications CASCADE;
DROP TABLE IF EXISTS students CASCADE;
DROP TABLE IF EXISTS programs CASCADE;
DROP TABLE IF EXISTS faculties CASCADE;

CREATE TABLE faculties (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE programs (
    id SERIAL PRIMARY KEY,
    faculty_id INTEGER NOT NULL REFERENCES faculties(id),
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE students (
    id BIGSERIAL PRIMARY KEY,
    program_id INTEGER NOT NULL REFERENCES programs(id),
    admission_year SMALLINT NOT NULL CHECK (admission_year BETWEEN 2018 AND 2035),
    full_name TEXT NOT NULL,
    birth_date DATE NOT NULL,
    email TEXT NOT NULL,
    phone TEXT NOT NULL,
    passport_series TEXT NOT NULL,
    passport_number TEXT NOT NULL
);

CREATE TABLE applications (
    id BIGSERIAL PRIMARY KEY,
    program_id INTEGER NOT NULL REFERENCES programs(id),
    year SMALLINT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('submitted', 'accepted', 'rejected', 'withdrawn')
    ),
    applicant_full_name TEXT NOT NULL,
    applicant_email TEXT NOT NULL,
    applicant_phone TEXT NOT NULL,
    applicant_passport_series TEXT NOT NULL,
    applicant_passport_number TEXT NOT NULL
);

CREATE TABLE teachers (
    id SERIAL PRIMARY KEY,
    full_name TEXT NOT NULL
);

CREATE TABLE courses (
    id SERIAL PRIMARY KEY,
    teacher_id INTEGER NOT NULL REFERENCES teachers(id),
    name TEXT NOT NULL
);

CREATE TABLE grades (
    id BIGSERIAL PRIMARY KEY,
    student_id BIGINT NOT NULL REFERENCES students(id),
    course_id INTEGER NOT NULL REFERENCES courses(id),
    grade SMALLINT NOT NULL CHECK (grade BETWEEN 2 AND 5),
    semester SMALLINT NOT NULL CHECK (semester BETWEEN 1 AND 8)
);

CREATE INDEX idx_programs_faculty_id ON programs(faculty_id);
CREATE INDEX idx_students_program_id ON students(program_id);
CREATE INDEX idx_students_admission_year ON students(admission_year);
CREATE INDEX idx_applications_program_id ON applications(program_id);
CREATE INDEX idx_applications_year ON applications(year);
CREATE INDEX idx_courses_teacher_id ON courses(teacher_id);
CREATE INDEX idx_grades_student_id ON grades(student_id);
CREATE INDEX idx_grades_course_id ON grades(course_id);
