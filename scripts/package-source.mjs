// Package only source-controlled project paths; never user audio, environment files or caches.
import { mkdirSync, copyFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
const files = ['src', 'scripts', 'tests', 'docs', 'LICENSE', 'NOTICE', 'README.md', 'README_zh.md',
  'README.upstream.md', 'package.json', 'pnpm-lock.yaml', 'tsconfig.json', 'vite.config.ts', 'index.html',
  'public/icons', 'public/manifest.webmanifest', 'public/jsmediatags.min.js', '.gitignore', '.github'];
mkdirSync('public/source', { recursive: true });
execFileSync('tar', ['--exclude=__pycache__', '--exclude=*.pyc', '-czf', 'public/source/amll-speech-player.tar.gz', ...files], { stdio: 'inherit' });
copyFileSync('LICENSE', 'public/source/LICENSE.txt');
