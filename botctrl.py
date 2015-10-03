#!/usr/bin/env python2.7

import telebot
import cv2

import json
import logging
import argparse
import tempfile
import os
import base64

__author__ = 'vashchuk.denis@gmail.com'

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


TOKENS_DB_PATH = "tokens.json"
BOT_CONF_PATH = "bot.conf"


class Image(object):
    def __init__(self, frame):
        self.frame = frame

    def save(self, file_path):
        return cv2.imwrite(file_path, self.frame)

    def encode(self, extension=".png"):
        r, b = cv2.imencode(extension, self.frame)
        return b.tobytes()

    def show(self, caption='captured image'):
        cv2.imshow(caption, self.frame)
        cv2.waitKey(0)
        cv2.destroyAllWindows()


class CameraError(Exception):
    def __init__(self, message='camera error'):
        Exception.__init__(self, message)


class Camera(object):
    def __init__(self, device_index=0):
        self._cap = cv2.VideoCapture(device_index)

    def fetch_image(self):
        ret, frame = self._cap.read()

        if not ret:
            raise CameraError()

        return Image(frame)

    def free(self):
        self._cap.release()

    def __del__(self):
        self.free()


class Authenticator(object):
    def __init__(self, file_path):
        self.db_path = file_path
        self._tokens = {}

        self._load()

    def _load(self):
        if os.path.exists(self.db_path):
            with open(self.db_path, "r") as fd:
                try:
                    self._tokens.update(json.load(fd))
                except ValueError:
                    logger.error("can't load tokens from file \"%s\"" % self.db_path)

    def _save(self):
        with open(self.db_path, "w") as fd:
            return json.dump(self._tokens, fd)

    def save(self):
        return self._save()

    def _add_token(self, token):
        assert(token not in self._tokens)
        self._tokens[token] = []
        return token

    def add_generate_token(self):
        token = base64.b32encode(os.urandom(20)).upper()
        self._add_token(token)
        return token

    def _is_token_valid(self, token):
        return token in self._tokens

    def _remove_id(self, id):
        for token, ids in self._tokens.iteritems():
            if id in ids:
                ids.remove(id)
                return True

        return False

    def authenticate(self, token, id):

        if not self._is_token_valid(token) or token not in self._tokens:
            self._remove_id(id)
            return False

        if id not in self._tokens[token]:
            self._tokens[token].append(id)

        return True

    def is_id_authenticated(self, id):
        for token, ids in self._tokens.iteritems():
            if id in ids:
                return token
        return False


def capture_image(camera=0):
    return Camera(camera).fetch_image()


def run_webcam_bot():
    token = json.load(open(BOT_CONF_PATH, "r"))['token']

    bot = telebot.TeleBot(token)
    authenticator = Authenticator(TOKENS_DB_PATH)

    def send_auth_error(message):
        bot.reply_to(message, "You wasn't authenticated")

    @bot.message_handler(commands=['help'])
    def send_welcome(message):
        bot.reply_to(message, "Hello, how are you?")

    @bot.message_handler(commands=['start'])
    def send_welcome(message):
        token = message.text.split()[1] if len(message.text.split()) == 2 else None

        if token is not None and authenticator.authenticate(token, message.chat.id):
            bot.reply_to(message, "Authenticated")
        else:
            send_auth_error(message)

    @bot.message_handler(commands=['shoot'])
    def send_image(message):

        if not authenticator.is_id_authenticated(message.chat.id):
            send_auth_error(message)
            return False

        try:
            camera_idx = 0 if len(message.text.split()) == 1 else int(message.text.split()[-1])

            image = capture_image(camera_idx)
            image_path  = tempfile.mktemp(suffix='.jpg')
            image.save(image_path)

            with open(image_path, "rb") as fd:
                bot.send_photo(message.chat.id, fd)

            os.remove(image_path)
        except (OSError, IOError, CameraError) as e:
            bot.send_message(message.chat.id, "error occurred during image capturing: %s" % e.message)

    logger.debug('polling telegram messages')
    try:
        bot.polling()
    except (KeyboardInterrupt, SystemExit):
        authenticator.save()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", type=int, default=None, help="set the index of camera for image capturing")
    parser.add_argument("--generate-token", help="generate new token")
    args = parser.parse_args()

    if args.capture is not None:
        camera_idx = args.capture
        image = capture_image(camera_idx)
        image.show()
    elif args.generate_token:
        authenticator = Authenticator(TOKENS_DB_PATH)
        token = authenticator.add_generate_token()
        authenticator.save()
        print(token)
    else:
        run_webcam_bot()
