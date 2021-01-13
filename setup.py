from setuptools import setup, find_packages


setup(
    name="acdhDashboard",
    version="0.7.2",
    packages=find_packages(),
    scripts=['scripts/qos-script-update-redmine'],
    install_requires=[],
    author="Mateusz Zoltak",
    author_email="mzoltak@oeaw.ac.at",
    description="Package keeping ACDH's Redmine services registry up to date",
    license="MIT",
    project_urls={
        "Bug Tracker": "https://gitlab.com/acdh-oeaw/acdh-dashboard/issues",
        "Documentation": "https://gitlab.com/acdh-oeaw/acdh-dashboard/-/wikis/home",
        "Source Code": "https://gitlab.com/acdh-oeaw/acdh-dashboard/tree/master"
    }
)
