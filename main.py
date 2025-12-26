from InquirerPy import prompt
from InquirerPy.base.control import Choice
import subprocess

questions = [
    {
        "name": "type_choice",
        "message": "What do you want to download?",
        "type": "list",
        "choices": [
            Choice(name="Music", value="music"),
            Choice(name="Video", value="video")
        ]
    }
]

answers = prompt(questions)

if answers["type_choice"] == "music":
    # Run music script
    subprocess.run(["python", "./music/ytspdl/main.py"])
else:
    # Run video script
    subprocess.run(["python", "./video/download.py"])
