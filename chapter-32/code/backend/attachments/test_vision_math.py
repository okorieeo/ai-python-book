from django.test import SimpleTestCase

from attachments.vision_math import HIGH_RES, STANDARD, count_image_tokens, resized_size


class VisionMathTests(SimpleTestCase):
    """The expected numbers come from the table in Anthropic's vision documentation (checked November 2026)."""

    def test_token_cost_is_one_per_28_pixel_patch(self):
        self.assertEqual(count_image_tokens(1000, 1000), 1296)
        self.assertEqual(count_image_tokens(200, 200), 64)
        self.assertEqual(count_image_tokens(1092, 1092), 1521)
        self.assertEqual(count_image_tokens(2576, 1449), 4784)

    def test_small_images_are_left_alone(self):
        for size in [(200, 200), (1000, 1000), (1092, 1092)]:
            self.assertEqual(resized_size(*size), size)

    def test_standard_tier_matches_the_documented_sizes(self):
        self.assertEqual(resized_size(1920, 1080), (1456, 819))  # NOT (1568, 882): the token limit decides
        w, h = resized_size(2000, 1500)  # the documentation lists 1269 x 952; rounding may differ by one pixel
        self.assertLessEqual(abs(w - 1269), 1)
        self.assertEqual(h, 952)
        self.assertEqual(count_image_tokens(w, h), 1564)  # the cost, which is what matters, is identical
        self.assertEqual(resized_size(3840, 2160), (1456, 819))
        self.assertEqual(resized_size(1075, 1520), (924, 1307))  # an A4 scan: both sides under 1568 px, still shrunk

    def test_high_resolution_tier(self):
        self.assertEqual(resized_size(1920, 1080, HIGH_RES), (1920, 1080))
        self.assertEqual(resized_size(2000, 1500, HIGH_RES), (2000, 1500))
        self.assertEqual(resized_size(3840, 2160, HIGH_RES), (2576, 1449))

    def test_portrait_is_the_mirror_of_landscape(self):
        w, h = resized_size(1920, 1080)
        self.assertEqual(resized_size(1080, 1920), (h, w))

    def test_result_always_fits_and_keeps_the_shape(self):
        for width, height in [(4000, 3000), (9000, 300), (300, 9000), (1569, 1), (5000, 5000)]:
            w, h = resized_size(width, height)
            self.assertLessEqual(count_image_tokens(w, h), STANDARD.max_tokens, (width, height))
            self.assertLessEqual(max(w, h), STANDARD.max_edge, (width, height))
            expected_short = (min(width, height) * max(w, h)) / max(width, height)
            self.assertLessEqual(abs(min(w, h) - expected_short), 1, (width, height))

    def test_nonsense_sizes_are_refused(self):
        with self.assertRaises(ValueError):
            resized_size(0, 100)
