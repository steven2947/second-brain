"""正文定位测试：防止漏段、重复标题覆盖和版本漂移。"""

import unittest
from src.distillation.normalize import normalize_markdown, verify_span


class NormalizationTests(unittest.TestCase):
    """验证正文范围与可回读证据。"""

    def test_duplicate_headings_and_exclusions_preserve_spans(self):
        """重复标题不能覆盖；序言和尾注必须有排除记录。"""
        text = '# 序\n\n序言。\n\n# 正文\n\n开头。\n\n## 重复\n\n> 别人的话。\n\n## 重复\n\n末段。\n\n# 附录\n\n索引。\n'
        result = normalize_markdown(text, [{'start_heading': '正文', 'end_heading': '附录'}])
        paragraphs = result['paragraphs']
        self.assertEqual([p['text'] for p in paragraphs], ['开头。', '> 别人的话。', '末段。'])
        self.assertEqual(len({p['id'] for p in paragraphs}), 3)
        self.assertEqual(len({s['id'] for s in result['sections']}), 3)
        for p in paragraphs:
            self.assertEqual(text[p['start']:p['end']], p['text'])
        self.assertTrue(any('序' in s['title'] for s in result['excluded_sections']))
        self.assertTrue(any('附录' in s['title'] for s in result['excluded_sections']))

    def test_source_change_invalidates_evidence(self):
        """源内容改变不能继续使用旧指纹的证据。"""
        text = '# 正文\n\n内容。\n'
        result = normalize_markdown(text, [{'start_heading': '正文', 'end_heading': None}])
        p = result['paragraphs'][0]
        verify_span(text, result['source_sha256'], p['start'], p['end'], p['text'])
        with self.assertRaisesRegex(ValueError, 'SOURCE_VERSION_MISMATCH'):
            verify_span(text + '改动', result['source_sha256'], p['start'], p['end'], p['text'])

    def test_crlf_preserves_original_offsets(self):
        """Windows 换行必须正确分段并保留原始字节对应字符位置。"""
        text = '# 正文\r\n\r\n第一段。\r\n\r\n第二段。\r\n'
        result = normalize_markdown(text, [{'start_heading':'正文','end_heading':None}])
        self.assertEqual([p['text'] for p in result['paragraphs']], ['第一段。','第二段。'])
        for p in result['paragraphs']:
            verify_span(text,result['source_sha256'],p['start'],p['end'],p['text'])

    def test_unknown_or_reversed_range_is_rejected(self):
        """错误范围不得静默产出空书。"""
        for ranges in [[{'start_heading': '缺失', 'end_heading': None}],
                       [{'start_heading': '乙', 'end_heading': '甲'}]]:
            with self.assertRaises(ValueError):
                normalize_markdown('# 甲\n\n甲文\n# 乙\n\n乙文', ranges)


if __name__ == '__main__':
    unittest.main()
