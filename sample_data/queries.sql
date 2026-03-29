-- Employee Analytics Queries

-- Total salary by department
SELECT department, SUM(salary) as total_salary
FROM employees
GROUP BY department
ORDER BY total_salary DESC;

-- Employees who joined after 2022
SELECT name, joining_date
FROM employees
WHERE joining_date > '2022-01-01'
ORDER BY joining_date;

-- Average salary per department
SELECT
    department,
    AVG(salary) as avg_salary,
    COUNT(*) as headcount
FROM employees
GROUP BY department;

-- Top earners
SELECT name, salary
FROM employees
WHERE salary > 90000
ORDER BY salary DESC
LIMIT 5;
