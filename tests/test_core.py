import unittest

from shebang_sentry.core import inspect_header


def inspect(data, **kwargs):
    return inspect_header(data, executable=True, **kwargs)


class HeaderTests(unittest.TestCase):
    def codes(self, data):
        return {x["code"] for x in inspect(data)["findings"]}

    def test_direct_header(self):
        result = inspect(b"#!/bin/sh -eu\necho hi\n")
        self.assertEqual(result["kernel_argv"], ["/bin/sh", "-eu", "<script>"])
        self.assertEqual(result["assessment"], "no-findings")

    def test_kernel_does_not_split_optional_argument(self):
        result = inspect(b"#!/bin/sh -e -u\n")
        self.assertEqual(result["kernel_argv"], ["/bin/sh", "-e -u", "<script>"])
        self.assertEqual(result["assessment"], "review")
        self.assertEqual(result["findings"][0]["code"], "SB102")

    def test_plain_env(self):
        result = inspect(b"#!/usr/bin/env python3\n")
        self.assertEqual(result["env_command"], ["python3"])
        self.assertEqual(result["findings"], [])

    def test_unsplit_env(self):
        result = inspect(b"#!/usr/bin/env python3 -u\n")
        self.assertEqual(result["kernel_argv"], ["/usr/bin/env", "python3 -u", "<script>"])
        self.assertIn("SB007", self.codes(b"#!/usr/bin/env python3 -u\n"))

    def test_simple_env_split_forms(self):
        for form in [b"-S python3 -u", b"-Spython3 -u", b"--split-string=python3 -u"]:
            with self.subTest(form=form):
                result = inspect(b"#!/usr/bin/env " + form + b"\n")
                self.assertEqual(result["env_command"], ["python3", "-u"])
                self.assertTrue(result["notes"])
                self.assertEqual(result["findings"], [])

    def test_complex_env_is_not_falsely_predicted(self):
        for form in [
            b'-S python3 "-u"',
            b"-S ${PYTHON}",
            b"-S python3 \\c ignored",
            b"-S -i python3",
            b"-i python3",
            b"LANG=C python3",
        ]:
            with self.subTest(form=form):
                result = inspect(b"#!/usr/bin/env " + form + b"\n")
                self.assertIsNone(result["env_command"])
                self.assertEqual(result["assessment"], "review")

    def test_env_without_command(self):
        for header in [b"#!/usr/bin/env\n", b"#!/usr/bin/env -S\n"]:
            self.assertIn("SB007", self.codes(header))

    def test_bom_and_leading_whitespace(self):
        self.assertIn("SB002", self.codes(b"\xef\xbb\xbf#!/bin/sh\n"))
        self.assertIn("SB002", self.codes(b"\xff\xfe#\0!\0"))
        self.assertIn("SB003", self.codes(b" \n#!/bin/sh\n"))
        self.assertIn("SB001", self.codes(b"echo hi\n"))

    def test_crlf_and_nul(self):
        self.assertIn("SB004", self.codes(b"#!/bin/sh\r\n"))
        self.assertIn("SB005", self.codes(b"#!/bin/sh\0junk\n"))
        self.assertIsNone(inspect(b"#!/bin/sh\r\n")["kernel_argv"])

    def test_only_header_is_inspected(self):
        self.assertEqual(inspect(b"#!/bin/sh\n\0\xff\r")["findings"], [])

    def test_space_and_tab_trimming(self):
        result = inspect(b"#! \t/bin/sh\t-eu \t\n")
        self.assertEqual(result["kernel_argv"], ["/bin/sh", "-eu", "<script>"])

    def test_absolute_nonempty_policy(self):
        self.assertIn("SB006", self.codes(b"#! \t\n"))
        self.assertIn("SB006", self.codes(b"#!bin/sh\n"))

    def test_non_utf8_is_review_not_false_success(self):
        self.assertEqual(inspect(b"#!/bin/\xff\n")["assessment"], "review")

    def test_boundary_length(self):
        self.assertNotIn("SB101", self.codes(b"#!/" + b"a" * 252 + b"\n"))
        self.assertIn("SB101", self.codes(b"#!/" + b"a" * 253 + b"\n"))

    def test_missing_mode_and_explicit_skip(self):
        self.assertEqual(inspect_header(b"#!/bin/sh\n", executable=False)["assessment"], "blocked")
        self.assertEqual(inspect_header(b"#!/bin/sh\n")["assessment"], "review")
        result = inspect_header(b"#!/bin/sh\n", check_mode=False)
        self.assertFalse(result["mode_checked"])
        self.assertEqual(result["assessment"], "no-findings")

    def test_no_lf_short_header(self):
        self.assertEqual(inspect(b"#!/bin/sh")["kernel_argv"], ["/bin/sh", "<script>"])

    def test_quotes_in_path_are_literal(self):
        self.assertIn("SB107", self.codes(b"#!/bin/'sh'\n"))
        self.assertIn("SB107", self.codes(b"#!/usr/bin/env 'python3'\n"))
