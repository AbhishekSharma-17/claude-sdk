"""Sample Python application with intentional bugs for testing."""

import os
import json


def load_config(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def calculate_bonus(salary: float, performance: str) -> float:
    """Calculate bonus based on performance rating."""
    # BUG: missing 'excellent' case
    if performance == "good":
        return salary * 0.10
    elif performance == "average":
        return salary * 0.05
    else:
        return 0.0


def get_department_budget(department: str) -> int:
    budgets = {
        "Engineering": 500000,
        "Marketing": 200000,
        "HR": 150000,
        # BUG: Finance is missing
    }
    return budgets[department]  # will throw KeyError for Finance


def connect_database(host: str, port: int, db: str):
    # TODO: implement actual connection
    print(f"Connecting to {host}:{port}/{db}")
    password = "hardcoded_password_123"  # BUG: hardcoded secret
    return None


if __name__ == "__main__":
    config = load_config("config.json")
    print(config["app_name"])
