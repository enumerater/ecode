import { confirm, isCancel, cancel, note } from '@clack/prompts';
import pc from 'picocolors';
import { resumeStream } from './api.js';
import { handleSSEStream } from './sse.js';

function pauseRL(rl) {
    rl.pause();
    if (process.stdin.isTTY) process.stdin.setRawMode(false);
}

function resumeRL(rl) {
    if (process.stdin.isTTY) process.stdin.setRawMode(true);
    rl.resume();
}

/**
 * Create an approval_required handler bound to a specific session.
 *
 * Returns a callback suitable for handleSSEStream's onApprovalRequired.
 * Internally manages readline pause/resume and recursive stream processing
 * so the caller doesn't need to know about approval internals.
 */
export function createApprovalHandler(config, threadId, rl, streamCallbacks) {
    return async function onApprovalRequired(data) {
        console.log('');
        const args = data.args || {};
        const lines = [`工具: ${data.tool_name}`];

        if (args.path) lines.push(`路径: ${args.path}`);
        if (args.command) lines.push(`命令: ${args.command}`);
        if (args.pattern) lines.push(`模式: ${args.pattern}`);
        if (args.old_string) {
            lines.push(`替换:\n  - ${args.old_string.slice(0, 200)}`);
            lines.push(`  + ${args.new_string?.slice(0, 200) || ''}`);
        }
        if (args.content && !args.old_string) {
            const preview = args.content.slice(0, 500);
            lines.push(`内容:\n${preview}${args.content.length > 500 ? '\n...' : ''}`);
        }

        note(lines.join('\n'), '需要审批');

        pauseRL(rl);
        try {
            const approved = await confirm({ message: '允许执行此操作？' });
            if (isCancel(approved)) {
                cancel('已取消');
                return;
            }

            const approval = approved ? 'approved' : 'rejected';
            console.log(pc.gray(`  ${approved ? '已批准' : '已拒绝'}，继续...`));

            const res = await resumeStream(config, { threadId, approval });
            await handleSSEStream(res.data, streamCallbacks);
        } catch (err) {
            console.log(pc.red(`恢复失败: ${err.message}`));
        } finally {
            resumeRL(rl);
        }
    };
}
