from setuptools import setup, find_packages

setup(
    name="breathing_monitor",
    version="1.0.0",
    description="Breathing monitor with Acconeer 60GHz radar and video streaming capabilities.",
    author="Your Name",
    author_email="your.email@example.com",
    url="https://github.com/yourusername/breathing_monitor",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "acconeer-exptool",  # Add other Acconeer tools if needed
        "websockets",
        "opencv-python",
        "numpy",
    ],
    entry_points={
        "console_scripts": [
            "breathing_monitor=breathing_monitor.main:main"
        ]
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.7',
)
