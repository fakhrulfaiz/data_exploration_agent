import { createServerClient } from "@supabase/ssr";
import { type NextRequest, NextResponse } from "next/server";

export const updateSession = async (request: NextRequest) => {
    // Create an unmodified response
    let response = NextResponse.next({
        request: {
            headers: request.headers,
        },
    });

    const supabase = createServerClient(
        process.env.NEXT_PUBLIC_SUPABASE_URL!,
        process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
        {
            cookies: {
                getAll() {
                    return request.cookies.getAll();
                },
                setAll(cookiesToSet) {
                    cookiesToSet.forEach(({ name, value }) =>
                        request.cookies.set(name, value)
                    );
                    response = NextResponse.next({
                        request: {
                            headers: request.headers,
                        },
                    });
                    cookiesToSet.forEach(({ name, value, options }) =>
                        response.cookies.set(name, value, options)
                    );
                },
            },
        }
    );

    // This will refresh session if needed - required for Server Components
    // https://supabase.com/docs/guides/auth/server-side/nextjs
    const {
        data: { user },
    } = await supabase.auth.getUser();

    // Protect routes - Redirect unauthenticated users
    // Modify this list to include all public routes
    const publicRoutes = [
        "/login",
        "/signup",
        "/forgot-password",
        "/auth/confirm",
        "/auth/callback"
    ];

    const isPublicRoute = publicRoutes.some(path => request.nextUrl.pathname.startsWith(path));

    // If user is NOT logged in and trying to access a protected route
    if (!user && !isPublicRoute) {
        // Clone the URL to redirect to login
        const url = request.nextUrl.clone();
        url.pathname = "/login";
        // Optional: Add redirect param to return after login
        // url.searchParams.set("next", request.nextUrl.pathname);
        return NextResponse.redirect(url);
    }

    // If user IS logged in and is trying to access auth pages, redirect to home
    // (Optional, good UX)
    const authRoutes = ["/login", "/signup", "/forgot-password"];
    if (user && authRoutes.some(path => request.nextUrl.pathname.startsWith(path))) {
        const url = request.nextUrl.clone();
        url.pathname = "/";
        return NextResponse.redirect(url);
    }

    return response;
};
