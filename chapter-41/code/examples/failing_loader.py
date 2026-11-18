import json


def load_settings(text):
    return json.loads(text)


def main():
    text = '{\n  "api_key": "sk-ant-FAKEKEY1234567890abcdef",\n  "owner": "ada@example.com",\n}\n'
    return load_settings(text)


if __name__ == "__main__":
    main()
