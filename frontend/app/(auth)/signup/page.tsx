"use client";

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
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

export default function SignUp() {
    const router = useRouter();
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [repeatPassword, setRepeatPassword] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState(false);

    const handleSignUp = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);
        setLoading(true);

        if (!password) {
            setError('Password is required');
            setLoading(false);
            return;
        }

        if (password !== repeatPassword) {
            setError('Passwords do not match');
            setLoading(false);
            return;
        }

        try {
            const supabase = createClient();
            const { error: signUpError } = await supabase.auth.signUp({
                email,
                password,
                options: {
                    emailRedirectTo: `${window.location.origin}/auth/callback`,
                },
            });

            if (signUpError) {
                throw signUpError;
            }

            setSuccess(true);
        } catch (err: any) {
            setError(err?.message || 'An error occurred during signup');
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
                                <CardTitle className="text-2xl">Thank you for signing up!</CardTitle>
                                <CardDescription>Check your email to confirm</CardDescription>
                            </CardHeader>
                            <CardContent>
                                <p className="text-sm text-muted-foreground">
                                    You've successfully signed up. Please check your email to confirm your account
                                    before signing in.
                                </p>
                                <div className="mt-4">
                                    <Button variant="outline" className="w-full" onClick={() => router.push('/login')}>
                                        Back to Login
                                    </Button>
                                </div>
                            </CardContent>
                        </Card>
                    ) : (
                        <Card>
                            <CardHeader>
                                <CardTitle className="text-2xl">Sign up</CardTitle>
                                <CardDescription>Create a new account</CardDescription>
                            </CardHeader>
                            <CardContent>
                                <form onSubmit={handleSignUp}>
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
                                        <div className="grid gap-2">
                                            <Label htmlFor="password">Password</Label>
                                            <Input
                                                id="password"
                                                name="password"
                                                type="password"
                                                value={password}
                                                onChange={(e) => setPassword(e.target.value)}
                                                required
                                            />
                                        </div>
                                        <div className="grid gap-2">
                                            <Label htmlFor="repeat-password">Repeat Password</Label>
                                            <Input
                                                id="repeat-password"
                                                name="repeat-password"
                                                type="password"
                                                value={repeatPassword}
                                                onChange={(e) => setRepeatPassword(e.target.value)}
                                                required
                                            />
                                        </div>
                                        {error && <p className="text-sm text-destructive">{error}</p>}
                                        <Button type="submit" className="w-full" disabled={loading}>
                                            {loading ? 'Creating an account...' : 'Sign up'}
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
