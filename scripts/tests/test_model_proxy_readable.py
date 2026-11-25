"""Synthetic coverage for human-readable exchange reports; no private fixtures."""

import copy
import json
from pathlib import Path
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
from model_proxy_diagnostics import ReloadableTemplates, display_text, json_value, readable, request_view, response_view
from model_proxy_report_preview import legacy_contexts


class ReadableReportTests(unittest.TestCase):
    def render(self, context):
        templates = ReloadableTemplates(chat_path=None, report_path=str(SCRIPTS / 'templates/model-proxy-readable-exchange.jinja'))
        snapshot = templates.snapshot()
        self.assertIsNone(templates.last_error)
        return snapshot.render_report(context)

    def common(self):
        return {'route': 'fixture/external:codex', 'request_id': 'fixture-request', 'correlation': {}, 'model': 'fixture'}

    def test_request_is_readable_in_order_and_payload_is_not_mutated(self):
        payload = {'model': 'fixture', 'instructions': 'First paragraph.\n\nSecond paragraph.',
            'input': [{'role': 'user', 'content': [{'type': 'input_text', 'text': 'first user'}]},
                {'type': 'function_call', 'name': 'terminal', 'call_id': 'call_a', 'arguments': json.dumps({'code': 'print(1)\nprint(2)'})},
                {'type': 'function_call_output', 'call_id': 'call_a', 'output': json.dumps({'stdout': 'line one\nline two', 'returncode': 0})},
                {'role': 'user', 'content': [{'type': 'input_text', 'text': 'latest user {{ 7 * 7 }}'}]}],
            'tools': [{'type': 'function', 'name': 'terminal', 'description': 'Execute code.\nPreserve lines.', 'parameters': {'type': 'object', 'properties': {'code': {'type': 'string'}}}}]}
        before = copy.deepcopy(payload)
        text = self.render({**request_view(payload, path='/v1/responses'), **self.common(), 'event': 'request', 'request_bytes': 100})
        self.assertEqual(payload, before)
        self.assertIn('LATEST USER MESSAGE — input 4', text)
        self.assertIn('latest user {{ 7 * 7 }}', text)
        self.assertNotIn('latest user 49', text)
        self.assertIn('Overview copy', text)
        positions = [text.index('--- INPUT %02d ---' % index) for index in range(1, 5)]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('TOOL CALL: terminal', text)
        self.assertIn('TOOL RESULT: terminal', text)
        self.assertIn('print(1)\n    print(2)', text)
        self.assertIn('line one\n  line two', text)
        self.assertIn('First paragraph.\n\nSecond paragraph.', text)
        self.assertNotIn('First paragraph.\\n', text)
        self.assertLess(text.index('CONVERSATION'), text.index('TOOL CATALOG'))

    def test_response_leads_with_plain_assistant_text_and_compact_usage(self):
        payload = {'object': 'response', 'id': 'resp_fixture', 'status': 'completed', 'output': [
            {'type': 'message', 'role': 'assistant', 'phase': 'final_answer', 'content': [{'type': 'output_text', 'text': 'Answer line one.\n\nAnswer line two.'}]}],
            'usage': {'input_tokens': 20642, 'output_tokens': 17, 'total_tokens': 20659,
                'input_tokens_details': {'cached_tokens': 0},
                'attribution': {'request_fields': {'instructions': {'input_tokens': 6056}, 'tools': {'input_tokens': 6478}}}}}
        text = self.render({**response_view(None, payload, transport_complete=True), **self.common(), 'event': 'response', 'status': 200})
        self.assertIn('Answer line one.\n\nAnswer line two.', text)
        self.assertNotIn('"output_text"', text)
        self.assertIn('input=20642 | cached=0 | output=17 | total=20659', text)
        self.assertIn('tools: input=6478', text)
        self.assertIn('provider_complete=True', text)

    def test_chat_completions_history_and_tool_link_are_preserved(self):
        payload = {'model': 'fixture', 'messages': [
            {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'cc_call', 'type': 'function', 'function': {'name': 'lookup', 'arguments': '{"q":"fixture"}'}}]},
            {'role': 'tool', 'tool_call_id': 'cc_call', 'content': '{"result":"one\\ntwo"}'},
            {'role': 'user', 'content': 'new question'}],
            'tools': [{'type': 'function', 'function': {'name': 'lookup', 'description': 'Find facts.', 'parameters': {'type': 'object'}, 'strict': True}}]}
        text = self.render({**request_view(payload, path='/v1/chat/completions'), **self.common(), 'event': 'request', 'request_bytes': 10})
        self.assertIn('protocol: chat_completions', text)
        self.assertIn('TOOL RESULT: lookup', text)
        self.assertIn('one\n  two', text)
        self.assertIn('strict: true', text)

    def test_opaque_and_unknown_items_are_labelled_without_losing_their_presence(self):
        secret_blob = 'opaque' * 1000
        payload = {'input': [{'type': 'reasoning', 'encrypted_content': secret_blob},
                             {'type': 'future_item', 'new_field': 'KEEP_UNKNOWN'},
                             {'role': 'user', 'content': [{'type': 'input_image', 'image_url': 'data:image/png;base64,' + 'X' * 1000}]}]}
        text = self.render({**request_view(payload, path='/responses'), **self.common(), 'event': 'request', 'request_bytes': 10})
        self.assertIn('opaque encrypted content: 6000 chars', text)
        self.assertNotIn(secret_blob, text)
        self.assertIn('KEEP_UNKNOWN', text)
        self.assertIn('inline media:', text)
        self.assertIn('--- INPUT 03 ---', text)

    def test_partial_stream_and_non_json_errors_remain_visible(self):
        view = response_view('data: {"type":"response.output_text.delta","delta":"partial answer"}\n\n', None, transport_complete=False)
        text = self.render({**view, **self.common(), 'event': 'response', 'status': 200})
        self.assertIn('partial answer', text)
        self.assertIn('transport_complete=False', text)
        self.assertIn('provider_complete=False', text)

    def test_display_filters_do_not_reinterpret_ordinary_text_or_terminal_controls(self):
        self.assertEqual(json_value('not JSON {{ 7*7 }}'), 'not JSON {{ 7*7 }}')
        self.assertEqual(json_value('{bad JSON'), '{bad JSON')
        self.assertEqual(json_value('{"message":"one\\ntwo"}'), {'message': 'one\ntwo'})
        self.assertEqual(display_text('\x1b[31mtext\r\n'), '\\x1b[31mtext\\x0d\n')
        self.assertEqual(readable({'body': 'one\ntwo'}), 'body:\n  one\n  two')

    def test_preview_refuses_mismatched_attachment_pair(self):
        request = '[request | route=fixture | request=one]\n'
        response = '[response | route=fixture | request=two]\n'
        with self.assertRaisesRegex(ValueError, 'do not match'):
            legacy_contexts(request, response)


if __name__ == '__main__':
    unittest.main()
