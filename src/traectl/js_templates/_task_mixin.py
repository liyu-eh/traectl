# ── TaskMixin ──────────────────────────────────────────────────

def type_command_palette(json_cmd):
    return f"""
    (function() {{
        var input = document.querySelector('.monaco-inputbox input');
        if (input) {{ input.focus(); input.value = {json_cmd}; input.dispatchEvent(new Event('input', {{bubbles: true}})); return 'typed'; }}
        return 'no input';
    }})()
    """


def toggle_auto_mode(selector, json_enable):
    return f"""
    (function() {{
        var sw = document.querySelector('{selector}');
        if (!sw) return '未找到自动模式开关';
        if (sw.checked !== {json_enable}) {{
            sw.click();
            return '自动模式已' + ({json_enable} ? '开启' : '关闭');
        }}
        return '自动模式已是' + ({json_enable} ? '开启' : '关闭') + '状态';
    }})()
    """


def query_tasks_detailed(selectors):
    return f"""
    (function() {{
        var taskList = document.querySelector('{selectors["task_list"]}');
        if (!taskList) {{ return JSON.stringify([]); }}
        var items = taskList.querySelectorAll('{selectors["task_item"]}');
        var tasks = [];
        for (var i = 0; i < items.length; i++) {{
            var title = items[i].querySelector('[class*="title"]');
            tasks.push({{
                index: i,
                title: title ? title.textContent.trim().substring(0, 100) : items[i].textContent.trim().substring(0, 100)
            }});
        }}
        return JSON.stringify(tasks, null, 2);
    }})()
    """


def click_task_item(selectors, task_index):
    return f"""
    (function() {{
        var items = document.querySelectorAll('{selectors["task_item"]}');
        if ({task_index} < 0 || {task_index} >= items.length) {{
            return '任务索引越界，共 ' + items.length + ' 个任务';
        }}
        items[{task_index}].click();
        return '已切换到任务 ' + {task_index};
    }})()
    """


def click_delete_task_btn(selectors):
    return f"""
    (function() {{
        var btns = document.querySelectorAll('button, [role="button"]');
        for (var i = 0; i < btns.length; i++) {{
            var text = btns[i].textContent.trim();
            if (text === '删除' || text === 'Delete') {{
                btns[i].click();
                return '已点击删除';
            }}
        }}
        var delIcons = document.querySelectorAll('{selectors["delete_task_icon"]}');
        if (delIcons.length > 0) {{ delIcons[0].click(); return '已点击删除图标'; }}
        return '未找到删除按钮';
    }})()
    """


def click_stop_btn():
    return """
    (function() {
        var sendBtn = document.querySelector('.chat-input-v2-send-button');
        if (sendBtn && !sendBtn.disabled) {
            var stopIcon = sendBtn.querySelector('.codicon-stop-circle');
            if (stopIcon && stopIcon.offsetWidth > 0 && stopIcon.offsetHeight > 0) {
                sendBtn.click();
                return '已停止生成';
            }
        }
        var btns = document.querySelectorAll('button');
        for (var i = 0; i < btns.length; i++) {
            var cls = btns[i].className || '';
            if (cls.indexOf('stop') !== -1 || cls.indexOf('cancel') !== -1) {
                btns[i].click();
                return '已停止生成';
            }
            var title = btns[i].getAttribute('title') || '';
            if (title.indexOf('停止') !== -1 || title.indexOf('Stop') !== -1) {
                btns[i].click();
                return '已停止生成';
            }
        }
        return '未找到停止按钮（可能不在生成中）';
    })()
    """


def type_quick_open(json_path):
    return f"""
    (function() {{
        var input = document.querySelector('.monaco-inputbox input, .quick-open-input input');
        if (!input) return 'no input found';
        input.value = {json_path};
        input.dispatchEvent(new Event('input', {{bubbles: true}}));
        return 'typed';
    }})()
    """
