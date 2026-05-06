#!/usr/bin/env node
import { loadConfig } from './cli/config.js';
import { startChat } from './cli/chat.js';

startChat(loadConfig());
