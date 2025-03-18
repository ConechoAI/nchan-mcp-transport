from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="httmcp",
    version="0.2.0",
    author="lloydzhou",
    author_email="lloydzhou@qq.com",
    description="HTTP MCP Transport for Nchan",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/conechoai/nchan-mcp-transport",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    python_requires=">=3.10",
    install_requires=[
        "fastapi>=0.115.11",
        "httpx>=0.27.0",
        "openapi-httpx-client>=0.4.1",
        "mcp>=1.3.0",
    ],
)