import { select, confirm, isCancel, cancel, note, log } from '@clack/prompts';
import pc from 'picocolors';
import readline from 'readline';
import crypto from 'crypto';
import { getProjectRoot } from './config.js';
import { chatStream, listSessions, deleteSession, getHistory } from './api.js';
import { handleSSEStream } from './sse.js';
import { createApprovalHandler } from './approval.js';
import {
    showBanner, showSessionInfo, showHelp,
    formatText, formatToolCall, formatToolResult, formatUsage, formatError, formatTime
} from './display.js';

function prompt(rl) {
    return new Promise((resolve) => {
        rl.question(pc.cyan('> '), (answer) => resolve(answer));
    });
}

function pauseRL(rl) {
    rl.pause();
    if (process.stdin.isTTY) process.stdin.setRawMode(false);
}

function resumeRL(rl) {
    if (process.stdin.isTTY) process.stdin.setRawMode(true);
    rl.resume();
}

/**
 * Build the SSE callback map for a given session.
 * The approval handler is created fresh each time so it captures the current threadId
 * and can recursively process new streams from resumeStream.
 */
function buildStreamCallbacks(config, threadId, rl) {
    const callbacks = {
        onText: formatText,
        onToolCall: formatToolCall,
        onToolResult: formatToolResult,
        onUsage: formatUsage,
        onError: formatError,
        onDone() {}
    };
    callbacks.onApprovalRequired = createApprovalHandler(config, threadId, rl, callbacks);
    return callbacks;
}

async function processStream(response, config, threadId, rl) {
    const callbacks = buildStreamCallbacks(config, threadId, rl);
    await handleSSEStream(response.data, callbacks);
}

// --- Slash command handlers ---

async function cmdSessions(config) {
    try {
        const sessions = await listSessions(config);
        if (!sessions?.length) { log.info('没有会话记录。'); return; }
        const lines = sessions.map(s => {
            const title = (s.title || '无标题').slice(0, 40);
            return `  ${pc.cyan(title)}  ${pc.gray(s.project_root || '')}  ${pc.yellow(formatTime(s.updated_at))}`;
        });
        note(lines.join('\n'), `共 ${sessions.length} 个会话`);
    } catch (err) {
        log.error(`获取失败: ${err.message}`);
    }
}

async function cmdSwitch(config, rl) {
    try {
        const sessions = await listSessions(config);
        if (!sessions?.length) { log.info('没有会话记录。'); return null; }
        pauseRL(rl);
        const choice = await select({
            message: '选择要切换的会话：',
            options: sessions.map(s => ({
                value: s.thread_id,
                label: s.title || s.thread_id.slice(0, 16),
                hint: formatTime(s.updated_at)
            }))
        });
        resumeRL(rl);
        if (isCancel(choice)) { cancel('已取消'); return null; }
        log.success(`已切换到会话 ${choice.slice(0, 16)}...`);
        return choice;
    } catch (err) {
        resumeRL(rl);
        log.error(`切换失败: ${err.message}`);
        return null;
    }
}

async function cmdDelete(config, currentId, rl) {
    try {
        const sessions = await listSessions(config);
        if (!sessions?.length) { log.info('没有会话记录。'); return false; }
        pauseRL(rl);
        const choice = await select({
            message: '选择要删除的会话：',
            options: sessions.map(s => ({
                value: s.thread_id,
                label: s.title || s.thread_id.slice(0, 16),
                hint: formatTime(s.updated_at)
            }))
        });
        if (isCancel(choice)) { resumeRL(rl); cancel('已取消'); return false; }
        const ok = await confirm({ message: '确认删除？' });
        resumeRL(rl);
        if (isCancel(ok) || !ok) { cancel('已取消'); return false; }
        await deleteSession(config, choice);
        log.success('会话已删除。');
        return choice === currentId;
    } catch (err) {
        resumeRL(rl);
        log.error(`删除失败: ${err.message}`);
        return false;
    }
}

async function cmdHistory(config, threadId) {
    try {
        const messages = await getHistory(config, threadId);
        if (!messages?.length) { log.info('没有消息记录。'); return; }
        for (const msg of messages) {
            if (msg.type === 'human') {
                console.log(pc.cyan(`\n[用户] ${msg.content}`));
            } else if (msg.type === 'ai') {
                console.log(pc.white(`\n[AI] ${msg.content}`));
            } else if (msg.type === 'tool') {
                const preview = (msg.content || '').slice(0, 100);
                console.log(pc.gray(`  [工具结果] ${preview}${msg.content?.length > 100 ? '...' : ''}`));
            }
        }
        console.log('');
    } catch (err) {
        log.error(`获取历史失败: ${err.message}`);
    }
}

// --- Main entry point ---

export async function startChat(config) {
    showBanner();

    let threadId = crypto.randomUUID();
    const projectRoot = getProjectRoot();

    const rl = readline.createInterface({
        input: process.stdin,
        output: process.stdout,
        historySize: 100,
        terminal: true
    });

    showSessionInfo(threadId, projectRoot);

    while (true) {
        const input = await prompt(rl);
        const trimmed = input.trim();
        if (!trimmed) continue;

        if (trimmed.startsWith('/')) {
            const cmd = trimmed.split(/\s+/)[0].toLowerCase();
            switch (cmd) {
                case '/help':
                    showHelp(); break;
                case '/sessions':
                    await cmdSessions(config); break;
                case '/switch': {
                    const newId = await cmdSwitch(config, rl);
                    if (newId) {
                        threadId = newId;
                        console.log(pc.gray(`当前会话: ${threadId.slice(0, 8)}`));
                    }
                    break;
                }
                case '/new':
                    threadId = crypto.randomUUID();
                    console.log(pc.green(`新会话: ${threadId.slice(0, 8)}`));
                    break;
                case '/delete': {
                    const deleted = await cmdDelete(config, threadId, rl);
                    if (deleted) {
                        threadId = crypto.randomUUID();
                        console.log(pc.gray(`已自动创建新会话: ${threadId.slice(0, 8)}`));
                    }
                    break;
                }
                case '/history':
                    await cmdHistory(config, threadId); break;
                case '/clear':
                    console.clear();
                    console.log(pc.bgCyan(pc.black(' ecode-cli 代码智能体 ')));
                    console.log(pc.gray(`会话: ${threadId.slice(0, 8)}\n`));
                    break;
                case '/exit':
                    console.log('再见！');
                    rl.close();
                    process.exit(0);
                default:
                    console.log(pc.yellow(`未知命令: ${cmd}，输入 /help 查看可用命令`));
            }
            continue;
        }

        try {
            const response = await chatStream(config, {
                prompt: trimmed,
                projectRoot,
                threadId
            });
            await processStream(response, config, threadId, rl);
        } catch (err) {
            console.log(pc.red('错误：'), err.message || '连接失败');
        }
        console.log('');
    }
}
