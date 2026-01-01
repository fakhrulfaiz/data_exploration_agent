'use client';

import React, { useState } from 'react';
import {
    Dialog,
    DialogContent,
    DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { Settings, User, X } from 'lucide-react';
import DarkModeToggle from './DarkModeToggle';
import { cn } from '@/lib/utils';

interface SettingsDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
}

type TabType = 'general' | 'personalization';

const SettingsDialog: React.FC<SettingsDialogProps> = ({ open, onOpenChange }) => {
    const [activeTab, setActiveTab] = useState<TabType>('general');

    // Profile state
    const [nickname, setNickname] = useState('');
    const [role, setRole] = useState('');
    const [aboutUser, setAboutUser] = useState('');
    const [customInstructions, setCustomInstructions] = useState('');
    const [communicationStyle, setCommunicationStyle] = useState<'concise' | 'detailed' | 'balanced'>('balanced');

    const tabs = [
        { id: 'general' as TabType, label: 'General', icon: Settings },
        { id: 'personalization' as TabType, label: 'Personalization', icon: User },
    ];

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-4xl h-[600px] p-0 gap-0 overflow-hidden" showCloseButton={false}>
                <DialogTitle className="sr-only">Settings</DialogTitle>
                <div className="flex h-full overflow-hidden">
                    {/* Left Sidebar */}
                    <div className="w-56 border-r bg-muted/30 flex flex-col">
                        {/* Header */}
                        <div className="p-4 border-b">
                            <h2 className="text-lg font-semibold">Settings</h2>
                        </div>

                        {/* Tabs */}
                        <nav className="flex-1 p-2">
                            {tabs.map((tab) => {
                                const Icon = tab.icon;
                                return (
                                    <button
                                        key={tab.id}
                                        onClick={() => setActiveTab(tab.id)}
                                        className={cn(
                                            "w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-colors mb-1",
                                            activeTab === tab.id
                                                ? "bg-background text-foreground shadow-sm"
                                                : "text-muted-foreground hover:bg-background/50 hover:text-foreground"
                                        )}
                                    >
                                        <Icon className="w-4 h-4" />
                                        {tab.label}
                                    </button>
                                );
                            })}
                        </nav>
                    </div>

                    {/* Right Content */}
                    <div className="flex-1 flex flex-col min-h-0">
                        {/* Header with Close */}
                        <div className="flex items-center justify-between px-6 py-4 border-b flex-shrink-0">
                            <h3 className="text-lg font-semibold">
                                {tabs.find(t => t.id === activeTab)?.label}
                            </h3>
                            <button
                                onClick={() => onOpenChange(false)}
                                className="rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
                            >
                                <X className="h-4 w-4" />
                                <span className="sr-only">Close</span>
                            </button>
                        </div>

                        {/* Content */}
                        <div className="flex-1 overflow-y-auto px-6 py-6 min-h-0">
                            {activeTab === 'general' && (
                                <div className="space-y-6 max-w-2xl">
                                    <div>
                                        <h4 className="text-sm font-semibold mb-3">Appearance</h4>
                                        <div className="flex items-center justify-between py-2">
                                            <Label htmlFor="theme" className="text-sm">Theme</Label>
                                            <DarkModeToggle size="sm" />
                                        </div>
                                    </div>
                                </div>
                            )}

                            {activeTab === 'personalization' && (
                                <div className="space-y-6 max-w-2xl">
                                    {/* Communication Style */}
                                    <div className="space-y-3">
                                        <div>
                                            <h4 className="text-sm font-semibold mb-1">Base style and tone</h4>
                                            <p className="text-xs text-muted-foreground">
                                                Set the style and tone of how the agent responds to you. This doesn't impact the agent's capabilities.
                                            </p>
                                        </div>
                                        <div className="space-y-2">
                                            <Label htmlFor="communication-style" className="text-sm">Communication Style</Label>
                                            <Select value={communicationStyle} onValueChange={(value: any) => setCommunicationStyle(value)}>
                                                <SelectTrigger id="communication-style" className="w-full">
                                                    <SelectValue />
                                                </SelectTrigger>
                                                <SelectContent>
                                                    <SelectItem value="concise">Concise</SelectItem>
                                                    <SelectItem value="detailed">Detailed</SelectItem>
                                                    <SelectItem value="balanced">Balanced</SelectItem>
                                                </SelectContent>
                                            </Select>
                                        </div>
                                    </div>

                                    {/* Custom Instructions */}
                                    <div className="space-y-3">
                                        <div>
                                            <h4 className="text-sm font-semibold mb-1">Custom instructions</h4>
                                            <p className="text-xs text-muted-foreground">
                                                Additional behavior, style, and tone preferences
                                            </p>
                                        </div>
                                        <Textarea
                                            placeholder="e.g., Always provide code examples, prefer Python over JavaScript..."
                                            value={customInstructions}
                                            onChange={(e) => setCustomInstructions(e.target.value)}
                                            className="min-h-[100px] resize-none"
                                        />
                                    </div>

                                    {/* About You */}
                                    <div className="space-y-3 border-t pt-6">
                                        <h4 className="text-sm font-semibold">About you</h4>

                                        <div className="space-y-2">
                                            <Label htmlFor="nickname" className="text-sm">Nickname</Label>
                                            <Input
                                                id="nickname"
                                                placeholder="Faiz"
                                                value={nickname}
                                                onChange={(e) => setNickname(e.target.value)}
                                            />
                                        </div>

                                        <div className="space-y-2">
                                            <Label htmlFor="role" className="text-sm">Role</Label>
                                            <Input
                                                id="role"
                                                placeholder="e.g., Data Analyst, Student, Developer..."
                                                value={role}
                                                onChange={(e) => setRole(e.target.value)}
                                            />
                                        </div>

                                        <div className="space-y-2">
                                            <Label htmlFor="about-user" className="text-sm">About</Label>
                                            <Textarea
                                                id="about-user"
                                                placeholder="Tell the agent about yourself, your work, interests..."
                                                value={aboutUser}
                                                onChange={(e) => setAboutUser(e.target.value)}
                                                className="min-h-[100px] resize-none"
                                            />
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    );
};

export default SettingsDialog;
