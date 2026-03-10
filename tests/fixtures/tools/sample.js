import { readFile } from 'fs';

export const API_URL = "https://example.com";

export function greet(name) {
    return `Hello, ${name}!`;
}

function helper(x) {
    return x * 2;
}

export class Widget {
    constructor(id) {
        this.id = id;
    }

    render() {
        return `<div>${this.id}</div>`;
    }
}
