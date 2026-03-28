-- Sample SQL: Employee reporting query with CTE, JOIN, aggregation
-- Used by Claude Agent SDK tool demos

CREATE TABLE employees (
    id INT PRIMARY KEY,
    name VARCHAR(100),
    department_id INT,
    salary DECIMAL(10, 2),
    hire_date DATE
);

CREATE TABLE departments (
    id INT PRIMARY KEY,
    name VARCHAR(100),
    budget DECIMAL(12, 2)
);

-- CTE: Top earners per department
WITH dept_stats AS (
    SELECT
        d.name AS department_name,
        COUNT(e.id) AS employee_count,
        AVG(e.salary) AS avg_salary,
        MAX(e.salary) AS max_salary
    FROM employees e
    INNER JOIN departments d ON e.department_id = d.id
    WHERE e.hire_date >= '2020-01-01'
    GROUP BY d.name
)
SELECT
    department_name,
    employee_count,
    ROUND(avg_salary, 2) AS avg_salary,
    max_salary,
    CASE
        WHEN avg_salary > 100000 THEN 'High'
        WHEN avg_salary > 70000 THEN 'Medium'
        ELSE 'Low'
    END AS salary_tier
FROM dept_stats
WHERE employee_count >= 3
ORDER BY avg_salary DESC;
