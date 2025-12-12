"use client";

import { useMemo, useState, useId } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ThemeToggle } from "@/components/theme-toggle";
import { AgentService } from "@/services";
import type { AgentRequest, AgentResponse } from "@/types";

interface Message {
    id: string;
    content: string;
    role: "user" | "assistant";
    timestamp: Date;
}

export default function Home() {
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState("");
    const [isLoading, setIsLoading] = useState(false);
    const reactId = useId();
    const sessionId = useMemo(() => `session-${reactId}`, [reactId]);

    const sendMessage = async () => {
        if (!input.trim() || isLoading) return;

        const userMessage: Message = {
            id: `user-${Date.now()}`,
            content: input.trim(),
            role: "user",
            timestamp: new Date(),
        };

        setMessages((prev) => [...prev, userMessage]);
        setInput("");
        setIsLoading(true);

        try {
            const response: AgentResponse = await AgentService.runAgent(
                userMessage.content,
                sessionId
            );

            // Add assistant messages - safely access nested data
            const messages = response.data?.messages || [];
            messages.forEach((content, index) => {
                if (content && content.trim()) {
                    const assistantMessage: Message = {
                        id: `assistant-${Date.now()}-${index}`,
                        content: content.trim(),
                        role: "assistant",
                        timestamp: new Date(),
                    };
                    setMessages((prev) => [...prev, assistantMessage]);
                }
            });
        } catch (error) {
            const errorMessage: Message = {
                id: `error-${Date.now()}`,
                content: `Error: ${error instanceof Error ? error.message : "Something went wrong"}`,
                role: "assistant",
                timestamp: new Date(),
            };
            setMessages((prev) => [...prev, errorMessage]);
        } finally {
            setIsLoading(false);
        }
    };

    const handleKeyPress = (e: React.KeyboardEvent) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    };

    return (
        <div className="min-h-screen bg-background p-4">
            <div className="mx-auto max-w-4xl">
                <Card className="h-[80vh]">
                    <CardHeader>
                        <div className="flex items-center justify-between">
                            <div>
                                <CardTitle>SQL Agent Chat</CardTitle>
                                <p className="text-muted-foreground text-sm">
                                    Ask questions about your database and get intelligent responses
                                </p>
                            </div>
                            <ThemeToggle />
                        </div>
                    </CardHeader>
                    <CardContent className="flex flex-col h-full gap-4">
                        {/* Messages Area */}
                        <ScrollArea className="flex-1 pr-4">
                            <div className="space-y-4">
                                {messages.length === 0 ? (
                                    <div className="text-center text-muted-foreground py-8">
                                        <p>No messages yet. Start by asking a question about your database!</p>
                                        <p className="text-sm mt-2">
                                            Try: "What tables are available?" or "Show me the first 5 customers"
                                        </p>
                                    </div>
                                ) : (
                                    messages.map((message) => (
                                        <div
                                            key={message.id}
                                            className={`flex ${message.role === "user" ? "justify-end" : "justify-start"
                                                }`}
                                        >
                                            <div
                                                className={`max-w-[80%] rounded-lg px-4 py-2 ${message.role === "user"
                                                    ? "bg-primary text-primary-foreground"
                                                    : "bg-muted text-muted-foreground"
                                                    }`}
                                            >
                                                <p className="whitespace-pre-wrap">{message.content}</p>
                                                <p className="text-xs opacity-70 mt-1">
                                                    {message.timestamp.toLocaleTimeString()}
                                                </p>
                                            </div>
                                        </div>
                                    ))
                                )}
                                {isLoading && (
                                    <div className="flex justify-start">
                                        <div className="bg-muted text-muted-foreground rounded-lg px-4 py-2">
                                            <p>Thinking...</p>
                                        </div>
                                    </div>
                                )}
                            </div>
                        </ScrollArea>

                        {/* Input Area */}
                        <div className="flex gap-2">
                            <Textarea
                                value={input}
                                onChange={(e) => setInput(e.target.value)}
                                onKeyDown={handleKeyPress}
                                placeholder="Ask a question about your database..."
                                className="flex-1 min-h-[60px] resize-none"
                                disabled={isLoading}
                            />
                            <Button
                                onClick={sendMessage}
                                disabled={!input.trim() || isLoading}
                                className="self-end"
                            >
                                Send
                            </Button>
                        </div>

                        {/* Status */}
                        <div className="text-xs text-muted-foreground text-center">
                            Session: {sessionId} • Connected to SQL Agent
                        </div>
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}
