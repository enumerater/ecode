import { createParser } from 'eventsource-parser';

const EVENT_MAP = {
    text: 'onText',
    tool_call: 'onToolCall',
    tool_result: 'onToolResult',
    approval_required: 'onApprovalRequired',
    usage: 'onUsage',
    error: 'onError',
    done: 'onDone'
};

/**
 * Process an SSE stream with ordered async callbacks.
 *
 * Key invariant: the promise only resolves when BOTH:
 *   1. The underlying stream has ended
 *   2. Every queued handler (including long-running ones like approval) has completed
 *
 * This prevents the caller from returning to the input loop while an
 * approval_required handler is still waiting for user input.
 */
export function handleSSEStream(stream, callbacks) {
    return new Promise((resolve, reject) => {
        const queue = [];
        let processing = false;
        let streamEnded = false;

        function tryResolve() {
            if (streamEnded && queue.length === 0 && !processing) {
                resolve();
            }
        }

        async function processQueue() {
            if (processing) return;
            processing = true;
            while (queue.length > 0) {
                const { handlerName, data } = queue.shift();
                const handler = callbacks[handlerName];
                if (handler) {
                    await handler(data);
                }
            }
            processing = false;
            tryResolve();
        }

        const parser = createParser({
            onEvent(event) {
                const handlerName = EVENT_MAP[event.event];
                if (!handlerName) return;
                try {
                    const data = JSON.parse(event.data);
                    queue.push({ handlerName, data });
                    processQueue();
                } catch (err) {
                    reject(err);
                }
            }
        });

        stream.on('data', (chunk) => {
            parser.feed(chunk.toString());
        });

        stream.on('end', () => {
            streamEnded = true;
            tryResolve();
        });

        stream.on('error', (err) => {
            reject(err);
        });
    });
}
