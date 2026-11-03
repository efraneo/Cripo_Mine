from setuptools import setup, find_packages

setup(
    name="el_bot_de_efra",
    version="1.0.0",
    author="Efra",
    description="Bot de trading inteligente con IA, estrategias técnicas, Telegram, backtesting y Streamlit.",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    packages=find_packages(exclude=["tests", "logs", "data"]),
    include_package_data=True,
    install_requires=[
        "streamlit>=1.35.0",
        "pandas>=2.2.2",
        "numpy>=1.26.4",
        "scikit-learn>=1.4.1",
        "yfinance>=0.2.36",
        "python-telegram-bot==13.15",
        "python-dotenv>=1.0.1",
        "plotly>=5.22.0",
        "matplotlib>=3.9.0",
        "tqdm>=4.66.4",
        "ta>=0.11.0"
    ],
    entry_points={
        "console_scripts": [
            "bot-efra=el_bot_de_efra:ejecutar_bot",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3.9",
        "License :: OSI Approved :: MIT License",  # ✅ Línea correcta
        "Operating System :: OS Independent",
        "Intended Audience :: Developers",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    license="MIT",  # ✅ Esto va aquí
    python_requires=">=3.9",
)
