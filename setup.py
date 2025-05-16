from setuptools import setup, find_packages

setup(
    name="bardkeeper",
    version="0.1.0",
    description="CLI tool for managing rsync-based archive operations",
    author="Claude",
    packages=find_packages(),
    install_requires=[
        "tinydb>=4.0.0",
        "rich>=10.0.0",
        "rich-click>=1.0.0",
        "simple-term-menu>=1.4.0",
    ],
    extras_require={
        "dev": [
            "pytest>=6.0.0",
            "pytest-cov>=2.10.0",
        ],
        "schedule": [
            "croniter>=1.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "bardkeeper=bardkeeper:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: System Administrators",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Topic :: System :: Archiving :: Backup",
        "Topic :: Utilities",
    ],
    python_requires=">=3.7",
)
