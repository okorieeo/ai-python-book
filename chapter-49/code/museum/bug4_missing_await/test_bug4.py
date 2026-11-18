import unittest

from museum.bug4_missing_await.support import FakeChannelLayer
from museum.impl import load

impl = load("museum.bug4_missing_await", ("buggy", "fixed"))


class NotifierTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_message_reaches_the_group(self):          # regression test
        layer = FakeChannelLayer()
        await impl.AnswerNotifier(layer).notify(7, "done")
        self.assertEqual(layer.delivered, [("conv-7", {"type": "answer.ready", "text": "done"})])


if __name__ == "__main__":
    unittest.main()
