import { EventEmitter } from 'events';

export const VERSION = "1.0.0";

export function processData(input: string): string {
    return input.trim();
}

function internalHelper(n: number): number {
    return n + 1;
}

export class DataStore {
    private items: string[] = [];

    add(item: string): void {
        this.items.push(item);
    }

    getAll(): string[] {
        return [...this.items];
    }
}
