import { note } from '@clack/prompts';
import pc from 'picocolors';

// --- Tool display name mapping ---
const TOOL_LABELS = {
    view_file: '查看文件',
    edit_file: '编辑文件',
    write_file: '写入文件',
    create_file: '创建文件',
    create_directory: '创建目录',
    search_code: '搜索代码',
    list_files: '列出文件',
    run_command: '执行命令'
};

function toolLabel(name) {
    return TOOL_LABELS[name] || name;
}

// Track tool_call_id → tool_name mapping
const toolCallMap = new Map();

// --- Tool call detail formatting ---

function formatToolCallArgs(toolName, args) {
    if (!args) return '';
    switch (toolName) {
        case 'view_file':
            return args.path
                + (args.start_line ? ` (行 ${args.start_line}-${args.end_line || '末尾'})` : '');
        case 'edit_file':
            return args.path || '';
        case 'write_file':
        case 'create_file':
            return args.path || '';
        case 'create_directory':
            return args.path || '';
        case 'search_code':
            return `"${args.pattern || ''}" in ${args.path || '.'}`
                + (args.include_pattern ? ` [${args.include_pattern}]` : '');
        case 'list_files':
            return (args.path || '.')
                + (args.max_depth ? ` (深度 ${args.max_depth})` : '');
        case 'run_command':
            return args.command || '';
        default:
            return '';
    }
}

// --- Tool result detail formatting ---

function formatResultDetail(toolName, data) {
    if (!data || typeof data !== 'object') {
        return pc.green('  ✓ 完成');
    }

    const success = data.success !== false;
    const error = data.error || data.message || '';

    if (!success) {
        return pc.red(`  ✗ 失败: ${error || '未知错误'}`);
    }

    switch (toolName) {
        case 'view_file': {
            const content = data.content || '';
            if (!content) return pc.gray('  ✓ 文件为空');
            const lines = content.split('\n');
            const preview = lines.slice(0, 8).join('\n');
            const suffix = lines.length > 8 ? pc.gray(`\n  ... 共 ${lines.length} 行`) : '';
            return pc.green(`  ✓ ${lines.length} 行\n`) + pc.gray(preview) + suffix;
        }
        case 'edit_file':
            return pc.green('  ✓ 替换成功');
        case 'write_file':
        case 'create_file': {
            const size = data.bytes || data.size || 0;
            return pc.green('  ✓ 已写入') + (size ? pc.gray(` (${size} bytes)`) : '');
        }
        case 'create_directory':
            return pc.green('  ✓ 目录已创建');
        case 'search_code': {
            const results = data.results || data.matches || [];
            if (!results.length && !data.count) return pc.gray('  ✓ 无匹配结果');
            const count = data.count || results.length;
            if (results.length) {
                const preview = results.slice(0, 5).map(r =>
                    typeof r === 'string' ? r : `${r.file || ''}:${r.line || ''}  ${(r.content || r.text || '').trim()}`
                ).join('\n');
                const suffix = count > 5 ? pc.gray(`\n  ... 共 ${count} 处匹配`) : '';
                return pc.green(`  ✓ ${count} 处匹配\n`) + pc.gray(preview) + suffix;
            }
            return pc.green(`  ✓ ${count} 处匹配`);
        }
        case 'list_files': {
            const dirs = data.directories || [];
            const files = data.files || [];
            const all = [...dirs, ...files];
            const total = data.total || all.length;
            if (!all.length) return pc.gray('  ✓ 空目录');
            const preview = all.slice(0, 15).join('\n');
            const suffix = total > 15 ? pc.gray(`\n  ... 共 ${total} 项`) : '';
            return pc.gray(preview) + suffix;
        }
        case 'run_command': {
            const exitCode = data.exit_code ?? data.exitCode;
            const exitStr = exitCode != null
                ? (exitCode === 0 ? pc.green(' ✓ exit 0') : pc.red(` ✗ exit ${exitCode}`))
                : '';
            const output = data.output || data.stdout || '';
            if (!output) return pc.gray('  (无输出)') + exitStr;
            const lines = output.split('\n');
            const preview = lines.slice(-10).join('\n');
            const prefix = lines.length > 10 ? pc.gray(`  ... 省略 ${lines.length - 10} 行\n`) : '';
            return prefix + pc.gray(preview) + exitStr;
        }
        default:
            return pc.green('  ✓ 完成');
    }
}

// --- Public API ---

export function showBanner() {
    console.clear();
    console.log(pc.bgCyan(pc.black(' ecode-cli 代码智能体 ')) + '\n');
}

export function showSessionInfo(threadId, projectRoot) {
    console.log(pc.gray(`会话: ${threadId.slice(0, 8)}  项目: ${projectRoot}`));
    console.log(pc.gray(`输入 /help 查看可用命令\n`));
}

export function showHelp() {
    const cmds = [
        ['/help', '显示此帮助'],
        ['/sessions', '列出所有会话'],
        ['/switch', '切换会话'],
        ['/new', '新建会话'],
        ['/delete', '删除会话'],
        ['/history', '查看当前会话历史'],
        ['/clear', '清屏'],
        ['/exit', '退出'],
    ];
    const lines = cmds.map(
        ([cmd, desc]) => `  ${pc.cyan(cmd.padEnd(12))} ${desc}`
    );
    note(lines.join('\n'), '可用命令');
}

export function formatText(data) {
    if (data?.chunk) process.stdout.write(data.chunk);
}

export function formatToolCall(data) {
    const toolName = data.tool_name || '';
    // Track tool_call_id → tool_name for matching with tool_result
    if (data.tool_call_id) {
        toolCallMap.set(data.tool_call_id, toolName);
    }
    const label = toolLabel(toolName);
    const detail = formatToolCallArgs(toolName, data.args);
    console.log(pc.blue(`\n> ${label}`) + (detail ? pc.gray(` ${detail}`) : '') + pc.blue(' ...'));
}

export function formatToolResult(data) {
    // Resolve tool name via tool_call_id mapping
    const toolName = data?.tool_call_id
        ? toolCallMap.get(data.tool_call_id) || ''
        : '';
    // Clean up mapping after use
    if (data?.tool_call_id) {
        toolCallMap.delete(data.tool_call_id);
    }

    // Parse the result field — backend sends it as a JSON string
    let parsed = data;
    if (typeof data?.result === 'string') {
        try {
            parsed = JSON.parse(data.result);
        } catch {
            // If parse fails, show raw result string
            console.log(pc.gray(`  ${data.result.slice(0, 300)}`));
            return;
        }
    } else if (data?.result && typeof data.result === 'object') {
        parsed = data.result;
    }

    console.log(formatResultDetail(toolName, parsed));
}

export function formatUsage(data) {
    const prompt = data.prompt_tokens ?? 0;
    const completion = data.completion_tokens ?? 0;
    const total = data.total_tokens ?? (prompt + completion);
    console.log(pc.gray(`\n  ⤷ 消耗: ${total} tokens (输入 ${prompt} + 输出 ${completion})`));
}

export function formatError(data) {
    console.log(pc.red(`\n错误: ${data.message}`));
}

export function formatTime(dateStr) {
    if (!dateStr) return '';
    const diff = Date.now() - new Date(dateStr);
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return '刚刚';
    if (mins < 60) return `${mins} 分钟前`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours} 小时前`;
    return `${Math.floor(hours / 24)} 天前`;
}
