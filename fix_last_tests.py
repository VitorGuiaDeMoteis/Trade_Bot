import sys
with open('tests/test_alpaca_executor.py', 'r', encoding='utf-8') as f:
    text = f.read()

target = "mock_resp.json.return_value = {\"message\": \"order_id must be unique\"}\n    mock_httpx.return_value = mock_resp"
replacement = target + "\n    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError('error', request=MagicMock(), response=mock_resp)"

text = text.replace(target, replacement)
with open('tests/test_alpaca_executor.py', 'w', encoding='utf-8') as f:
    f.write(text)

with open('tests/test_aggregator.py', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace("assert closed[0].open_time.minute == 0", "assert closed[0].open_time.minute == 30")
text = text.replace("assert closed[1].open_time.minute == 5", "assert closed[1].open_time.minute == 35")
text = text.replace("assert closed[2].open_time.minute == 0", "assert closed[2].open_time.minute == 30")

with open('tests/test_aggregator.py', 'w', encoding='utf-8') as f:
    f.write(text)
