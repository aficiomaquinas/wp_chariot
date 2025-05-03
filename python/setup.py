from setuptools import setup, find_packages

with open("requirements.txt", "r") as f:
    requirements = f.read().splitlines()

setup(
    name="wp-deploy-tools",
    version="0.1.0",
    packages=["commands", "utils", "sync", "tools"],
    include_package_data=True,
    install_requires=requirements,
    entry_points={
        'console_scripts': [
            'wp-deploy=cli:main',
        ],
    },
    author="Victor Gonzalez",
    author_email="victor@ttamayo.com",
    description="Herramientas de despliegue para WordPress",
    keywords="wordpress, deployment, tools",
    python_requires=">=3.8",
) 