# ── ChatMixin ──────────────────────────────────────────────────

def click_new_task_btn(selector):
    return f"""
    (function() {{
        var btn = document.querySelector('{selector}');
        if (btn) {{ btn.click(); return 'clicked'; }}
        return 'no new-task-button found';
    }})()
    """


def focus_input_box(selector):
    return f"""
    (function() {{
        var input = document.querySelector('{selector}');
        if (!input) {{ return 'no input element'; }}
        input.focus();
        // 清空内容：设置 innerHTML + 派发 input 事件
        input.innerHTML = '';
        input.dispatchEvent(new Event('input', {{bubbles: true, cancelable: true}}));
        return 'focused';
    }})()
    """


def verify_input_text(selector):
    return f"""
    (function() {{
        var input = document.querySelector('{selector}');
        if (!input) return 'no input';
        var text = '';
        try {{
            if (input.__lexicalEditor) {{
                var state = input.__lexicalEditor.getEditorState();
                state.read(function() {{ text = $getRoot().getTextContent(); }});
            }}
        }} catch(e) {{ text = input.textContent || ''; }}
        return text.substring(0, 80);
    }})()
    """


def click_send_btn(selector):
    return f"""
    (function() {{
        var btn = document.querySelector('{selector}');
        if (!btn) {{ return 'no send button'; }}
        var disabled = btn.disabled || btn.getAttribute('aria-disabled') === 'true';
        if (disabled) {{ return 'send button disabled'; }}
        btn.click();
        return 'sent';
    }})()
    """


def query_chat_content(selectors, max_length, constants):
    return f"""
    (function() {{
        var turns = document.querySelectorAll('section[data-role]');
        if (!turns.length) {{
            var container = document.querySelector('{selectors["chat_container"]}');
            return container ? container.textContent.trim().substring(0, {max_length}) : '{constants["NO_CHAT_CONTAINER"]}';
        }}
        var parts = [];
        for (var i = 0; i < turns.length; i++) {{
            var t = turns[i];
            var role = t.getAttribute('data-role');
            var msgContent = null;
            if (role === 'user') {{
                msgContent = t.querySelector('{selectors["user_msg_content"]}');
            }} else if (role === 'assistant') {{
                // assistant 消息内容在 assistant-chat-turn-content 中
                msgContent = t.querySelector('{selectors["assistant_msg_content"]}');
            }}
            if (msgContent) {{
                var text = msgContent.textContent.trim();
                if (text) parts.push(role + ': ' + text);
            }} else {{
                // 兜底：去掉 heading 后的内容
                var heading = t.querySelector('{selectors["chat_turn_heading"]}');
                if (heading) {{
                    var cloned = t.cloneNode(true);
                    var h = cloned.querySelector('{selectors["chat_turn_heading"]}');
                    if (h) h.remove();
                    var text = cloned.textContent.trim();
                    if (text) parts.push(text);
                }} else {{
                    var text = t.textContent.trim();
                    if (text) parts.push(text);
                }}
            }}
        }}
        return parts.join('\\n').substring(0, {max_length}) || '{constants["NO_CHAT_CONTENT"]}';
    }})()
    """


def query_chat_hash(selectors):
    return f"""
    (function() {{
        var turns = document.querySelectorAll('section[data-role]');
        if (!turns.length) {{
            var container = document.querySelector('{selectors["chat_container"]}');
            if (!container) return '';
            var text = container.textContent.trim();
            var short = text.length > 4000 ? text.substring(text.length - 2000) : text;
            var hash = 0, i, chr;
            for (i = 0; i < short.length; i++) {{
                chr = short.charCodeAt(i);
                hash = ((hash << 5) - hash) + chr;
                hash |= 0;
            }}
            return hash.toString();
        }}
        var parts = [];
        for (var i = 0; i < turns.length; i++) {{
            var t = turns[i];
            var role = t.getAttribute('data-role');
            var msgContent = null;
            if (role === 'user') {{
                msgContent = t.querySelector('{selectors["user_msg_content"]}');
            }} else if (role === 'assistant') {{
                msgContent = t.querySelector('{selectors["assistant_msg_content"]}');
            }}
            if (msgContent) {{
                parts.push(role + ':' + msgContent.textContent.trim());
            }} else {{
                var heading = t.querySelector('{selectors["chat_turn_heading"]}');
                if (heading) {{
                    var cloned = t.cloneNode(true);
                    var h = cloned.querySelector('{selectors["chat_turn_heading"]}');
                    if (h) h.remove();
                    parts.push(cloned.textContent.trim());
                }} else {{
                    parts.push(t.textContent.trim());
                }}
            }}
        }}
        var text = parts.join('|').trim();
        var short = text.length > 4000 ? text.substring(text.length - 2000) : text;
        var hash = 0, i, chr;
        for (i = 0; i < short.length; i++) {{
            chr = short.charCodeAt(i);
            hash = ((hash << 5) - hash) + chr;
            hash |= 0;
        }}
        return hash.toString();
    }})()
    """


def query_solo_status(selectors):
    return f"""
    (function() {{
        var input = document.querySelector('{selectors["input_box"]}');
        var sendBtn = document.querySelector('{selectors["send_btn"]}');
        var taskList = document.querySelector('{selectors["task_list"]}');
        var cur = document.querySelector('{selectors["model_trigger_value"]}');
        var status = {{
            inputText: input ? input.textContent.substring(0, 100).trim() : '',
            sendDisabled: sendBtn ? (sendBtn.disabled || sendBtn.getAttribute('aria-disabled') === 'true') : true,
            taskCount: taskList ? taskList.children.length : 0,
            currentModel: cur ? cur.textContent.trim() : '',
        }};
        // 排除 codicon 旋转动画（始终存在），只检测有实质性内容的 thinking 元素
        var thinkingEl = document.querySelector('.assistant-action-bar.generating, .chat-turn-status-thinking');
        if (!thinkingEl) {{
            var allThinking = document.querySelectorAll('{selectors["thinking_indicator"]}');
            for (var ti = 0; ti < allThinking.length; ti++) {{
                var te = allThinking[ti];
                if (te.offsetWidth > 0 && te.offsetHeight > 0 && !te.classList.contains('codicon') && te.textContent.trim().length > 0) {{
                    thinkingEl = te;
                    break;
                }}
            }}
        }}
        status.isThinking = thinkingEl !== null;
        // 与发送按钮交叉验证：没有停止图标则不可能是 thinking 态
        if (status.isThinking) {{
            var sendBtn4check = document.querySelector('.chat-input-v2-send-button');
            var hasStopIcon = sendBtn4check && !sendBtn4check.disabled && sendBtn4check.querySelector('.codicon-stop-circle, .codicon-stop');
            if (!hasStopIcon) {{
                status.isThinking = false;
            }}
        }}
        var openFolderEl = document.querySelector('{selectors["open_folder"]}');
        status.needsOpenFolder = openFolderEl !== null;
        return JSON.stringify(status);
    }})()
    """


def query_task_list(selectors):
    return f"""
    (function() {{
        var taskList = document.querySelector('{selectors["task_list"]}');
        if (!taskList) {{ return JSON.stringify([]); }}
        var items = taskList.querySelectorAll('{selectors["task_item"]}');
        var tasks = [];
        for (var i = 0; i < items.length; i++) {{
            var title = items[i].querySelector('[class*="title"]');
            var status = items[i].querySelector('[class*="status"]');
            tasks.push({{
                title: title ? title.textContent.trim().substring(0, 100) : '',
                status: status ? status.textContent.trim() : ''
            }});
        }}
        return JSON.stringify(tasks);
    }})()
    """


def click_confirm_btn(selector):
    return f"""
    (function() {{
        var deleteBtn = document.querySelector('{selector}');
        if (deleteBtn) {{
            deleteBtn.click();
            return 'confirmed inline: delete';
        }}
        var btns = document.querySelectorAll('button');
        for (var i = 0; i < btns.length; i++) {{
            var text = btns[i].textContent.trim();
            if (text === '确认') {{
                var rect = btns[i].getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) {{
                    btns[i].click();
                    return 'confirmed dialog: ok';
                }}
            }}
        }}
        return 'no confirmation needed';
    }})()
    """


def check_queue_status():
    return """
    (function() {
        // 排队提醒 alert
        var queueAlert = document.querySelector('.icube-component-alert .icube-alert-title');
        if (queueAlert) {
            if (queueAlert.textContent.indexOf('排队') >= 0 || queueAlert.textContent.indexOf('queue') >= 0) {
                return true;
            }
        }
        // 最后一条 assistant 消息含排队信息
        var allAssistants = document.querySelectorAll('section[data-role="assistant"]');
        if (allAssistants.length > 0) {
            var lastAssist = allAssistants[allAssistants.length - 1];
            var text = lastAssist.textContent.trim();
            if (text.indexOf('排队提醒') >= 0 || text.indexOf('排在第') >= 0) {
                return true;
            }
        }
        return false;
    })()
    """


def get_queue_info(fallback_text):
    return f"""
    (function() {{
        var alert = document.querySelector('.icube-component-alert .icube-alert-title');
        if (alert) {{
            return alert.textContent.trim().substring(0, 100);
        }}
        var allAssistants = document.querySelectorAll('section[data-role="assistant"]');
        if (allAssistants.length > 0) {{
            var lastAssist = allAssistants[allAssistants.length - 1];
            var text = lastAssist.textContent.trim();
            var match = text.match(/排在第\\s*\\d+\\s*位/);
            if (match) return match[0];
        }}
        return '{fallback_text}';
    }})()
    """


def get_last_turn_role():
    return """
    (function() {
        var allSections = document.querySelectorAll('section[data-role]');
        if (allSections.length > 0) {
            return allSections[allSections.length - 1].getAttribute('data-role');
        }
        return '';
    })()
    """


def check_is_generating():
    return """
    (function() {
        // 先排除排队状态（排队中不算 generating）
        var queueAlert = document.querySelector('.icube-component-alert .icube-alert-title');
        if (queueAlert) {
            var alertText = queueAlert.textContent.trim();
            if (alertText.indexOf('排队') >= 0 || alertText.indexOf('queue') >= 0) {
                return false;
            }
        }

        // 检测排队状态：遍历 assistant sections，检查是否有排队消息
        var allAssistants = document.querySelectorAll('section[data-role="assistant"]');
        if (allAssistants.length > 0) {
            var lastAssist = allAssistants[allAssistants.length - 1];
            var assistText = lastAssist.textContent.trim();
            if (assistText.indexOf('排队提醒') >= 0 || assistText.indexOf('排在第') >= 0) {
                return false;
            }
            // 检测等待状态（"等待中..."不含排队信息时也算生成未开始）
            if (assistText.indexOf('等待中') >= 0 && assistText.length < 200) {
                return false;
            }
        }

        // 核心特征：发送按钮内有 codicon-stop-circle（停止图标，表示生成中）
        var sendBtn = document.querySelector('.chat-input-v2-send-button');
        if (sendBtn) {
            var stopIcon = sendBtn.querySelector('.codicon-stop-circle, .codicon-stop');
            if (stopIcon && stopIcon.offsetWidth > 0 && stopIcon.offsetHeight > 0) {
                return true;
            }
            // 空闲图标（ArrowUp/Send）且disabled=false说明可发送
            var idleIcon = sendBtn.querySelector('.codicon-icube-ArrowUp, .codicon-send, .codicon-icube-Send');
            if (idleIcon && idleIcon.offsetWidth > 0 && idleIcon.offsetHeight > 0) {
                return false;  // 空闲态
            }
        }

        // 兜底特征：assistant-action-bar.generating 可见（生成中的操作栏）
        var generatingBar = document.querySelector('.assistant-action-bar.generating');
        if (generatingBar && generatingBar.offsetWidth > 0 && generatingBar.offsetHeight > 0) {
            return true;
        }

        return false;
    })()
    """
