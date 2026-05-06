import axios from 'axios';

export function chatStream(config, { prompt, projectRoot, threadId }) {
    return axios({
        method: 'POST',
        url: `${config.backend.url}/api/chat/stream`,
        data: {
            prompt,
            project_root: projectRoot,
            thread_id: threadId
        },
        responseType: 'stream',
        timeout: config.backend.timeout || 60000
    });
}

export function resumeStream(config, { threadId, approval }) {
    return axios({
        method: 'POST',
        url: `${config.backend.url}/api/chat/resume`,
        data: {
            thread_id: threadId,
            approval
        },
        responseType: 'stream',
        timeout: config.backend.timeout || 60000
    });
}

export async function listSessions(config) {
    const res = await axios.get(`${config.backend.url}/api/sessions`, {
        timeout: config.backend.timeout || 10000
    });
    return res.data;
}

export async function deleteSession(config, threadId) {
    const res = await axios.delete(`${config.backend.url}/api/sessions/${threadId}`, {
        timeout: config.backend.timeout || 10000
    });
    return res.data;
}

export async function getHistory(config, threadId) {
    const res = await axios.get(`${config.backend.url}/api/sessions/${threadId}/history`, {
        timeout: config.backend.timeout || 10000
    });
    return res.data;
}
