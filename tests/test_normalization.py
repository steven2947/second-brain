"""正文定位测试：防止漏段、重复标题覆盖和版本漂移。"""

import unittest
from src.distillation.normalize import normalize_markdown, verify_span


class NormalizationTests(unittest.TestCase):
    """验证正文范围与可回读证据。"""

    def test_included_paths_drop_excluded_ancestors_keep_body_parents(self):
        """self 为测试实例；排除区一二级祖先不得污染正文，正文父级仍须保留。"""
        text = ('# 推荐序\n\n第三方文字。\n\n## 推荐者说明\n\n说明。\n\n'
                '### 正文章\n\n作者开头。\n\n#### 合法子节\n\n作者细节。\n\n'
                '#### 同级子节\n\n另一细节。\n\n### 尾注\n\n参考资料。\n')
        result = normalize_markdown(text, [{'start_heading': '正文章', 'end_heading': '尾注'}])
        expected = ['正文章', '正文章 / 合法子节', '正文章 / 同级子节']
        self.assertEqual([s['path'] for s in result['sections']], expected)
        self.assertEqual([p['chapter'] for p in result['paragraphs']], expected)
        self.assertEqual([s['path'] for s in result['excluded_sections']],
                         ['推荐序', '推荐序 / 推荐者说明', '推荐序 / 推荐者说明 / 尾注'])
        self.assertEqual([p['text'] for p in result['paragraphs']],
                         ['作者开头。', '作者细节。', '另一细节。'])
        for p in result['paragraphs']:
            self.assertEqual(text[p['start']:p['end']], p['text'])

    def test_reentering_body_drops_only_excluded_heading_ancestors(self):
        """self 为测试实例；跨排除区重入时仅保留仍在标题栈中的已纳入父级。"""
        text = ('# 作者正文\n\n开头。\n\n## 第一节\n\n甲。\n\n'
                '## 排除插页\n\n第三方。\n\n### 插页说明\n\n旁注。\n\n'
                '#### 恢复正文\n\n乙。\n\n##### 内嵌论证\n\n丙。\n')
        ranges = [{'start_heading': '作者正文', 'end_heading': '排除插页'},
                  {'start_heading': '恢复正文', 'end_heading': None}]
        result = normalize_markdown(text, ranges)
        expected = ['作者正文', '作者正文 / 第一节', '作者正文 / 恢复正文',
                    '作者正文 / 恢复正文 / 内嵌论证']
        self.assertEqual([s['path'] for s in result['sections']], expected)
        self.assertEqual([p['chapter'] for p in result['paragraphs']], expected)
        self.assertEqual(result['excluded_sections'][-1]['path'],
                         '作者正文 / 排除插页 / 插页说明')
        self.assertEqual([p['text'] for p in result['paragraphs']], ['开头。', '甲。', '乙。', '丙。'])

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
