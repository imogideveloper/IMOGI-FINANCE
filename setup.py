from pathlib import Path

from setuptools import find_packages, setup

README = Path(__file__).with_name("README.md")

setup(
    name="imogi_finance",
    version=__import__("imogi_finance").__version__,
    description="App for Manage Expense IMOGI",
    long_description=README.read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    author="PT. Inovasi Terbaik Bangsa",
    author_email="m.abisena.putrawan@cao-group.co.id",
    license="mit",
    packages=find_packages(),
    include_package_data=True,
)
