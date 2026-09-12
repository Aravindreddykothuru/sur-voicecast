// Referenced by vitest.config.ts. Without this file the whole test run
// fails before collecting anything, which is how the frontend job stayed
// red on its first CI run.
import "@testing-library/jest-dom/vitest";
