filepath = r'C:\Users\pc\Desktop\lemme-do-it-for-you\agent\self_correcting_vision_agent_3.py'
with open(filepath, 'r') as f:
    content = f.read()

old_func_start = '    def _get_reestimate_prompt(self, target: str, nx: int, ny: int) -> str:'
old_marker = '    def _get_cropped_verification_path'

start_idx = content.find(old_func_start)
if start_idx >= 0:
    end_idx = content.find(old_marker, start_idx + 10)
    if end_idx >= 0:
        new_content = content[:start_idx] + content[end_idx:]
        with open(filepath, 'w') as f:
            f.write(new_content)
        print(f'Removed old function from char {start_idx} to {end_idx}')
    else:
        print('End marker not found')
else:
    print('Old function not found')
