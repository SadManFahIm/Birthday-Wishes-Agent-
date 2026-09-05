import re
from datetime import datetime
from pathlib import Path

import instaloader


SESSION_DIR = Path("sessions")
SESSION_DIR.mkdir(exist_ok=True)

KEYWORDS = [
    "happy birthday",
    "hbd",
    "birthday girl",
    "birthday boy",
    "birthday post",
    "bday",
    "birthday dump",
]


class InstagramBirthdayDetector:

    def __init__(self, username):
        self.username = username

        self.loader = instaloader.Instaloader(
            download_pictures=False,
            download_videos=False,
            download_comments=False,
            save_metadata=False,
        )

    def login(self, username, password):

        try:
            self.loader.login(username, password)

            self.loader.save_session_to_file(
                SESSION_DIR / f"{username}.session"
            )

            print("Instagram login success")

        except Exception as e:
            print("Instagram login failed:", e)

    def load_session(self, username):

        session_file = SESSION_DIR / f"{username}.session"

        if session_file.exists():

            self.loader.load_session_from_file(
                username,
                session_file,
            )

            print("Instagram session loaded")

    def detect_birthday_posts(self, target_username, limit=15):

        try:

            profile = instaloader.Profile.from_username(
                self.loader.context,
                target_username,
            )

            posts = profile.get_posts()

            detected = []

            for idx, post in enumerate(posts):

                if idx >= limit:
                    break

                caption = post.caption or ""

                text = caption.lower()

                found = any(
                    keyword in text
                    for keyword in KEYWORDS
                )

                birthday_date = self.extract_date(text)

                if found:

                    detected.append({
                        "username": target_username,
                        "caption": caption[:300],
                        "post_url": f"https://instagram.com/p/{post.shortcode}/",
                        "date": str(post.date.date()),
                        "birthday_date": birthday_date,
                    })

            return detected

        except Exception as e:
            print("Detection error:", e)
            return []

    def extract_date(self, text):

        patterns = [
            r'(\d{1,2}/\d{1,2}/\d{2,4})',
            r'(\d{1,2}-\d{1,2}-\d{2,4})',
        ]

        for pattern in patterns:

            match = re.search(pattern, text)

            if match:
                return match.group(1)

        return None


if __name__ == "__main__":

    detector = InstagramBirthdayDetector("your_username")

    # first time only
    # detector.login("your_username", "your_password")

    detector.load_session("your_username")

    result = detector.detect_birthday_posts(
        target_username="instagram",
        limit=10,
    )

    for post in result:
        print(post)