from setuptools import setup


APP = ["mac_app.py"]
OPTIONS = {
    "argv_emulation": False,
    "plist": {
        "CFBundleName": "Pomodoro",
        "CFBundleDisplayName": "Pomodoro",
        "CFBundleIdentifier": "com.xxzhuu.pomodoro",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1.0.0",
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
    },
    "packages": ["objc", "AppKit", "Foundation"],
}


setup(
    app=APP,
    name="Pomodoro",
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
