import '@fontsource-variable/inter';
import '../../fabparts-ux/src/app.css';
import '../../fabparts-ux/src/layout.css';
import { mount } from 'svelte';
import App from './App.svelte';
mount(App, { target: document.getElementById('app')! });
