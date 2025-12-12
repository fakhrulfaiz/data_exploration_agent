"use client";

import React, { useState } from 'react';
import { createClient } from '@/utils/supabase/client';
import { Button } from '@/components/ui/button';
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import Link from 'next/link';

export default function ForgotPassword() {
    const [email, setEmail] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState(false);

    const handleResetPassword = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);
        setLoading(true);

        try {
            const supabase = createClient();
            const { error: resetError } = await supabase.auth.resetPasswordForEmail(email, {
                redirectTo: `${window.location.origin}/auth/callback?next=/update-password`,
            });

            if (resetError) {
                throw resetError;
            }

            setSuccess(true);
        } catch (err: any) {
            setError(err?.message || 'An error occurred');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="flex min-h-screen w-full items-center justify-center p-6 md:p-10">
            <div className="w-full max-w-md">
                <div className="flex flex-col gap-6">
                    {success ? (
                        <Card>
                            <CardHeader>
                                <CardTitle className="text-2xl">Check Your Email</CardTitle>
                                <CardDescription>Password reset instructions sent</CardDescription>
                            </CardHeader>
                            <CardContent>
                                <p className="text-sm text-muted-foreground">
                                    If you registered using your email and password, you will receive a password reset
                                    email.
                                </p>
                                <div className="mt-4">
                                    <Link href="/login">
                                        <Button variant="outline" className="w-full">
                                            Back to Login
                                        </Button>
                                    </Link>
                                </div>
                            </CardContent>
                        </Card>
                    ) : (
                        <Card>
                            <CardHeader>
                                <CardTitle className="text-2xl">Reset Your Password</CardTitle>
                                <CardDescription>
                                    Type in your email and we'll send you a link to reset your password
                                </CardDescription>
                            </CardHeader>
                            <CardContent>
                                <form onSubmit={handleResetPassword}>
                                    <div className="flex flex-col gap-6">
                                        <div className="grid gap-2">
                                            <Label htmlFor="email">Email</Label>
                                            <Input
                                                id="email"
                                                name="email"
                                                type="email"
                                                placeholder="m@example.com"
                                                value={email}
                                                onChange={(e) => setEmail(e.target.value)}
                                                required
                                            />
                                        </div>
                                        {error && <p className="text-sm text-destructive">{error}</p>}
                                        <Button type="submit" className="w-full" disabled={loading}>
                                            {loading ? 'Sending...' : 'Send reset email'}
                                        </Button>
                                    </div>
                                    <div className="mt-4 text-center text-sm">
                                        Already have an account?{' '}
                                        <Link href="/login" className="underline underline-offset-4">
                                            Login
                                        </Link>
                                    </div>
                                </form>
                            </CardContent>
                        </Card>
                    )}
                </div>
            </div>
        </div>
    );
}
