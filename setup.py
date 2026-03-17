"""AI Video Factory — Package Setup."""

from setuptools import setup, find_packages
from pathlib import Path


def read_requirements():
    """Read requirements.txt, skipping comments and empty lines."""
    lines = Path("requirements.txt").read_text().splitlines()
    return [
        line.strip()
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    ]


setup(
    name="ai-video-factory",
    version="1.0.0",
    description="Automated Arabic documentary video production pipeline",
    author="Youssef Durgham",
    author_email="yusifdhrgamtrt@gmail.com",
    python_requires=">=3.11",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=read_requirements(),
    entry_points={
        "console_scripts": [
            "ai-video-factory=cli:main",
            "avf=cli:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
