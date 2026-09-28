CREATE DATABASE practice_db2;

USE practice_db2;

CREATE TABLE employees (
    emp_id INT PRIMARY KEY,
    first_name VARCHAR(50),
    last_name VARCHAR(50),
    department VARCHAR(50),
    salary DECIMAL(10, 2),
    hire_date DATE
);

INSERT INTO
    employees (
        emp_id,
        first_name,
        last_name,
        department,
        salary,
        hire_date
    )
VALUES (
        1,
        'John',
        'Doe',
        'IT',
        75000.00,
        '2021-03-15'
    ),
    (
        2,
        'Jane',
        'Smith',
        'HR',
        60000.00,
        '2020-06-01'
    ),
    (
        3,
        'Alice',
        'Johnson',
        'IT',
        85000.00,
        '2019-11-20'
    ),
    (
        4,
        'Bob',
        'Brown',
        'Finance',
        90000.00,
        '2018-01-10'
    ),
    (
        5,
        'Charlie',
        'Davis',
        'Finance',
        55000.00,
        '2022-08-05'
    );

SELECT * FROM employees;

SHOW DATABASES;

DROP DATABASE IF EXISTS practice_db1;

DROP DATABASE IF EXISTS practice_db;

SHOW DATABASES;

USE practice_db2;

DESCRIBE employees;

SELECT * FROM employees WHERE salary > 70000;

-- Find employees hired between 2020 and 2022
SELECT *
FROM employees
WHERE
    hire_date BETWEEN '2020-01-01' AND '2022-12-31';

-- Search by name pattern (First name starting with 'J' or 'A')
SELECT *
FROM employees
WHERE
    first_name LIKE 'J%'
    OR first_name LIKE 'A%';

-- Filter by a list of departments
SELECT * FROM employees WHERE department IN ('IT', 'Finance');

-- Count employees and calculate average salary per department
SELECT
    department,
    COUNT(*) AS total_employees,
    ROUND(AVG(salary), 2) AS avg_salary,
    MAX(salary) AS highest_salary,
    MIN(salary) AS lowest_salary
FROM employees
GROUP BY
    department;

-- Find departments with an average salary greater than 65,000
SELECT department, ROUND(AVG(salary), 2) AS avg_salary
FROM employees
GROUP BY
    department
HAVING
    AVG(salary) > 65000;

USE practice_db2;

-- Give a 10% salary bump to all IT employees
UPDATE employees
SET salary = salary * 1.10
WHERE department = 'IT';

-- Add a new column 'email' to the employees table
ALTER TABLE employees
ADD COLUMN email VARCHAR(100);

-- Update email address for an employee
UPDATE employees
SET email = 'john.doe@company.com'
WHERE emp_id = 1;