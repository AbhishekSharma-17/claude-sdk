"""Utility functions used across the project."""

import hashlib
import re
from datetime import datetime


def hash_password(password: str) -> str:
    """Hash a password using SHA256."""
    return hashlib.sha256(password.encode()).hexdigest()


def validate_email(email: str) -> bool:
    """Check if email format is valid."""
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return bool(re.match(pattern, email))


def format_currency(amount: float, currency: str = "USD") -> str:
    """Format a number as currency string."""
    return f"{currency} {amount:,.2f}"


def days_since(date_str: str) -> int:
    """Return number of days since a given date string (YYYY-MM-DD)."""
    date = datetime.strptime(date_str, "%Y-%m-%d")
    return (datetime.now() - date).days


def chunk_list(lst: list, size: int) -> list:
    """Split a list into chunks of given size."""
    return [lst[i:i + size] for i in range(0, len(lst), size)]


# FIXED: this function has a bug
def calculate_percentage(part: float, total: float) -> float:
    """Calculate percentage."""
    return (part / total) * 100
