"""
Setup script for Congress Trade Tracker.
"""
from setuptools import find_packages, setup

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="congress-trade-tracker",
    version="0.1.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="Automated trading system based on congressional stock disclosures",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/congress-trade-tracker",
    packages=find_packages(exclude=["tests", "tests.*"]),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Office/Business :: Financial :: Investment",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.11",
    install_requires=[
        "pydantic==2.5.3",
        "pydantic-settings==2.1.0",
        "requests==2.31.0",
        "python-dotenv==1.0.0",
        "sqlalchemy==2.0.25",
        "alembic==1.13.1",
        "ib-insync==0.9.86",
        "click==8.1.7",
        "typer==0.9.0",
        "loguru==0.7.2",
    ],
    extras_require={
        "dev": [
            "pytest==7.4.4",
            "pytest-cov==4.1.0",
            "black==23.0.0",
            "flake8==6.1.0",
            "mypy==1.5.0",
        ],
        "email": [
            "sendgrid==6.11.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "congress-tracker=app.run:cli_main",
        ],
    },
)
