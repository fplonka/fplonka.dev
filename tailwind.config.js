/** @type {import('tailwindcss').Config} */
module.exports = {
    content: [
        "./static/*.html",
        "./static/bpfreq/*.{html,js}",
        "./static/git-cluster/*.{html,js}",
        "./static/go-llca/*.{html,js}",
        "./static/organize-anything/skeleton.html",
    ],
    theme: {
        extend: {},
    },
    plugins: [],
    corePlugins: {
        preflight: false,
    },
};
