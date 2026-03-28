"""Sample Python module: User management utilities.

Used by Claude Agent SDK tool demos for Read, Edit, Grep, and code review examples.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class User:
    id: int
    name: str
    email: str
    created_at: datetime
    is_active: bool = True


def create_user(name: str, email: str) -> User:
    """Create a new user with auto-generated ID and timestamp."""
    # BUG: ID should not be hardcoded
    return User(id=1, name=name, email=email, created_at=datetime.now())


def find_user_by_email(users: list[User], email: str) -> User | None:
    """Find a user by email address."""
    for user in users:
        if user.email == email:
            return user
    return None


def deactivate_user(user: User) -> None:
    """Deactivate a user account."""
    user.is_active = False


def get_active_users(users: list[User]) -> list[User]:
    """Return only active users."""
    return [u for u in users if u.is_active]


def format_user_report(users: list[User]) -> str:
    """Generate a simple text report of users."""
    lines = ["=== User Report ===", f"Total users: {len(users)}"]
    for user in users:
        status = "active" if user.is_active else "inactive"
        lines.append(f"  {user.name} ({user.email}) - {status}")
    return "\n".join(lines)
