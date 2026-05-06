import fs from 'fs';
import path from 'path';
import yaml from 'js-yaml';

const DEFAULT_CONFIG = {
    backend: {
        url: 'http://127.0.0.1:8000',
        timeout: 30000
    }
};

export function loadConfig() {
    const configPath = path.join(process.cwd(), 'config.yaml');
    if (fs.existsSync(configPath)) {
        try {
            const raw = yaml.load(fs.readFileSync(configPath, 'utf8'));
            return { ...DEFAULT_CONFIG, ...raw, backend: { ...DEFAULT_CONFIG.backend, ...raw?.backend } };
        } catch { }
    }
    return DEFAULT_CONFIG;
}

export function getThreadId() {
    return Buffer.from(process.cwd()).toString('base64');
}

export function getProjectRoot() {
    return process.cwd().replace(/\\/g, '/');
}
