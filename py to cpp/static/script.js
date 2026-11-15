const pythonEditor = document.getElementById("pythonCode");
const cppCodeEditor = document.getElementById("cppCodeEditor");
const outputArea = document.getElementById("outputArea");
const astTreeContainer = document.getElementById("astTreeContainer");
const astControls = document.getElementById("astControls");
const convertBtn = document.getElementById("convertBtn");
const compileBtn = document.getElementById("compileBtn");
const runBtn = document.getElementById("runBtn");
const status = document.getElementById("status");
const terminalOutput = document.getElementById("terminalOutput");
const stdinInput = document.getElementById("stdinInput");
const exampleSelect = document.getElementById("exampleSelect");
const optimizeToggle = document.getElementById("optimizeToggle");
const historyList = document.getElementById("historyList");

let activeTab = "cpp";
let useInteractiveAst = true;
let conversionHistory = JSON.parse(localStorage.getItem("py2cpp_history") || "[]");

let outputs = {
    ast: "",
    ast_tree: null,
    analysis: "",
    ir: "",
    cpp: ""
};

const SAMPLES = {
    basic: `a = 10
b = 20
c = a + b
print("Sum:", c)`,

    functions: `def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)

def add(a, b=5):
    return a + b

print("5! =", factorial(5))
print("add(10) =", add(10))`,

    loops: `nums = [1, 2, 3, 4, 5, 6]
squares = [x * x for x in nums if x % 2 == 0]
print("Even squares:", squares)

total = 0
for i in range(10, 0, -2):
    total += i
print("Countdown sum:", total)`,

    collections: `scores = {"Alice": 92, "Bob": 85}
scores["Charlie"] = 98
print("Bob score:", scores["Bob"])

msg = "  hello python world  "
clean = msg.strip().upper()
print(f"Formatted: {clean}")`,

    oop: `class Animal:
    def __init__(self, name):
        self.name = name

    def speak(self):
        return self.name + " makes a sound"

class Dog(Animal):
    def __init__(self, name):
        self.name = name

    def speak(self):
        return self.name + " says Woof!"

d = Dog("Buddy")
print(d.speak())`,

    exceptions: `def safe_divide(a, b):
    try:
        if b == 0:
            raise ValueError("Cannot divide by zero")
        return a // b
    except ValueError as err:
        print("Caught error:", err)
        return -1

print("10 // 2 =", safe_divide(10, 2))
print("10 // 0 =", safe_divide(10, 0))`
};

function setTerminal(text, state = "normal") {
    terminalOutput.textContent = text;
    terminalOutput.classList.remove("terminal-error", "terminal-success");
    if (state === "error") terminalOutput.classList.add("terminal-error");
    if (state === "success") terminalOutput.classList.add("terminal-success");
}

function renderAstNode(node, isRoot = false) {
    const wrapper = document.createElement("div");
    wrapper.className = isRoot ? "ast-node root" : "ast-node";

    const hasChildren = Array.isArray(node.children) && node.children.length > 0;
    const header = document.createElement("div");
    header.className = "ast-node-header";

    const toggle = document.createElement("span");
    toggle.className = "ast-toggle";
    toggle.textContent = hasChildren ? "▼" : "•";
    header.appendChild(toggle);

    if (node.field) {
        const fieldSpan = document.createElement("span");
        fieldSpan.className = "ast-field";
        fieldSpan.textContent = `${node.field}: `;
        header.appendChild(fieldSpan);
    }

    const labelSpan = document.createElement("span");
    labelSpan.className = "ast-label";
    labelSpan.textContent = node.label || node.type;
    header.appendChild(labelSpan);

    if (node.line) {
        const lineSpan = document.createElement("span");
        lineSpan.className = "ast-line";
        lineSpan.textContent = `(line ${node.line})`;
        header.appendChild(lineSpan);
    }

    wrapper.appendChild(header);

    if (hasChildren) {
        const childContainer = document.createElement("div");
        childContainer.className = "ast-children";
        for (const child of node.children) {
            childContainer.appendChild(renderAstNode(child, false));
        }
        wrapper.appendChild(childContainer);

        header.addEventListener("click", () => {
            const collapsed = childContainer.classList.toggle("hidden");
            toggle.textContent = collapsed ? "▶" : "▼";
        });
    }

    return wrapper;
}

function displayOutput(tab) {
    activeTab = tab;

    cppCodeEditor.classList.add("hidden");
    astTreeContainer.classList.add("hidden");
    outputArea.classList.add("hidden");
    astControls.classList.add("hidden");

    if (tab === "cpp") {
        cppCodeEditor.classList.remove("hidden");
        cppCodeEditor.value = outputs.cpp || "";
    } else if (tab === "ast") {
        astControls.classList.remove("hidden");
        if (useInteractiveAst && outputs.ast_tree) {
            astTreeContainer.classList.remove("hidden");
            astTreeContainer.innerHTML = "";
            astTreeContainer.appendChild(renderAstNode(outputs.ast_tree, true));
        } else {
            outputArea.classList.remove("hidden");
            outputArea.textContent = outputs.ast || "No AST generated yet.";
        }
    } else {
        outputArea.classList.remove("hidden");
        outputArea.textContent = outputs[tab] || "No output generated yet.";
    }
}

function saveToHistory(pythonCode, cppCode) {
    const firstLine = pythonCode.split("\n").find((l) => l.trim()) || "snippet";
    const entry = {
        id: Date.now(),
        title: firstLine.slice(0, 34),
        time: new Date().toLocaleTimeString(),
        pythonCode,
        cppCode
    };
    conversionHistory = [entry, ...conversionHistory.slice(0, 7)];
    localStorage.setItem("py2cpp_history", JSON.stringify(conversionHistory));
    renderHistory();
}

function renderHistory() {
    historyList.innerHTML = "";
    if (!conversionHistory.length) {
        historyList.innerHTML = '<span class="muted">No conversions yet.</span>';
        return;
    }
    for (const item of conversionHistory) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "history-item";
        btn.textContent = `${item.title} (${item.time})`;
        btn.addEventListener("click", () => {
            pythonEditor.value = item.pythonCode;
            outputs.cpp = item.cppCode;
            displayOutput("cpp");
            status.textContent = "Loaded from history";
        });
        historyList.appendChild(btn);
    }
}

// Convert Python -> C++
convertBtn.addEventListener("click", async function () {
    const code = pythonEditor.value.trim();
    if (!code) {
        status.textContent = "Please enter Python code!";
        return;
    }

    convertBtn.disabled = true;
    convertBtn.textContent = "Transpiling...";
    status.textContent = "Parsing AST & inferring types...";

    try {
        const response = await fetch("/convert", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                code: code,
                optimize: optimizeToggle.checked
            })
        });

        const result = await response.json();

        if (!response.ok || !result.success) {
            throw new Error(result.error || "Transpilation failed");
        }

        outputs.ast = result.ast;
        outputs.ast_tree = result.ast_tree;
        outputs.analysis = JSON.stringify(result.analysis, null, 4);
        outputs.ir = result.intermediate_code;
        outputs.cpp = result.cpp;

        document.querySelectorAll(".tab").forEach((t) => {
            t.classList.toggle("active", t.dataset.tab === "cpp");
        });

        displayOutput("cpp");
        saveToHistory(code, result.cpp);
        status.textContent = result.message;
        setTerminal("Transpilation succeeded. Click 'Compile C++ (G++)' or 'Run Executable'.", "success");

    } catch (error) {
        setTerminal(error.message, "error");
        status.textContent = "Translation Error";
    } finally {
        convertBtn.disabled = false;
        convertBtn.textContent = "⚡ Convert to C++";
    }
});

// Compile C++ with G++
compileBtn.addEventListener("click", async function () {
    const cppCode = cppCodeEditor.value.trim();
    if (!cppCode) {
        setTerminal("No C++ code available to compile. Convert Python code first.", "error");
        return;
    }

    compileBtn.disabled = true;
    status.textContent = "Compiling with g++ -std=c++17...";

    try {
        const response = await fetch("/compile", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ cpp_code: cppCode })
        });
        const result = await response.json();
        if (!response.ok || !result.success) {
            throw new Error(result.error || "G++ compilation failed.");
        }
        status.textContent = "Compiled successfully";
        setTerminal(`${result.message}\n${result.compiler_output}`, "success");
    } catch (err) {
        status.textContent = "Compilation Error";
        setTerminal(err.message, "error");
    } finally {
        compileBtn.disabled = false;
    }
});

// Run Executable
runBtn.addEventListener("click", async function () {
    const cppCode = cppCodeEditor.value.trim();
    if (!cppCode) {
        setTerminal("No C++ code available to run. Convert Python code first.", "error");
        return;
    }

    runBtn.disabled = true;
    status.textContent = "Compiling & running binary...";

    try {
        const response = await fetch("/run", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                cpp_code: cppCode,
                stdin: stdinInput.value
            })
        });
        const result = await response.json();
        if (!response.ok || !result.success) {
            throw new Error(result.error || "Execution failed.");
        }
        status.textContent = `Exited with code ${result.exit_code}`;
        const outText = result.stdout ? result.stdout : "(Program produced no stdout)";
        setTerminal(outText, "success");
    } catch (err) {
        status.textContent = "Runtime / Compile Error";
        setTerminal(err.message, "error");
    } finally {
        runBtn.disabled = false;
    }
});

// Sample selector & Load Example button
document.getElementById("sampleBtn").addEventListener("click", function () {
    const key = exampleSelect.value || "basic";
    pythonEditor.value = SAMPLES[key] || SAMPLES.basic;
});

exampleSelect.addEventListener("change", function () {
    const key = exampleSelect.value;
    if (SAMPLES[key]) {
        pythonEditor.value = SAMPLES[key];
    }
});

// Upload .py file
document.getElementById("pyFileUpload").addEventListener("change", function (event) {
    const file = event.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = function (e) {
        pythonEditor.value = e.target.result;
        status.textContent = `Loaded ${file.name}`;
    };
    reader.readAsText(file);
});

// Clear / Reset
document.getElementById("clearBtn").addEventListener("click", function () {
    pythonEditor.value = "";
    cppCodeEditor.value = "";
    stdinInput.value = "";
    outputs = { ast: "", ast_tree: null, analysis: "", ir: "", cpp: "" };
    displayOutput(activeTab);
    setTerminal("Workspace cleared.", "normal");
    status.textContent = "Ready";
});

// Clear history
document.getElementById("clearHistoryBtn").addEventListener("click", function () {
    conversionHistory = [];
    localStorage.removeItem("py2cpp_history");
    renderHistory();
});

// Tab switching
document.querySelectorAll(".tab").forEach(function (tab) {
    tab.addEventListener("click", function () {
        document.querySelectorAll(".tab").forEach((item) => item.classList.remove("active"));
        tab.classList.add("active");
        displayOutput(tab.dataset.tab);
    });
});

// AST tree controls
document.getElementById("toggleAstViewBtn").addEventListener("click", function () {
    useInteractiveAst = !useInteractiveAst;
    this.textContent = useInteractiveAst ? "Switch to Raw AST Dump" : "Switch to Interactive Tree";
    displayOutput("ast");
});

document.getElementById("expandAllAstBtn").addEventListener("click", function () {
    astTreeContainer.querySelectorAll(".ast-children").forEach((el) => el.classList.remove("hidden"));
    astTreeContainer.querySelectorAll(".ast-toggle").forEach((el) => {
        if (el.textContent !== "•") el.textContent = "▼";
    });
});

document.getElementById("collapseAllAstBtn").addEventListener("click", function () {
    astTreeContainer.querySelectorAll(".ast-children").forEach((el) => el.classList.add("hidden"));
    astTreeContainer.querySelectorAll(".ast-toggle").forEach((el) => {
        if (el.textContent !== "•") el.textContent = "▶";
    });
});

// Copy output
document.getElementById("copyBtn").addEventListener("click", async function () {
    const textToCopy = activeTab === "cpp" ? cppCodeEditor.value : outputArea.textContent;
    try {
        await navigator.clipboard.writeText(textToCopy);
        status.textContent = "Copied to clipboard!";
    } catch (error) {
        status.textContent = "Could not copy output.";
    }
});

// Download .cpp file
document.getElementById("downloadCppBtn").addEventListener("click", function () {
    const content = cppCodeEditor.value || outputs.cpp;
    if (!content) {
        status.textContent = "Nothing to download yet.";
        return;
    }
    const blob = new Blob([content], { type: "text/x-c++src;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "output.cpp";
    a.click();
    URL.revokeObjectURL(url);
    status.textContent = "Downloaded output.cpp";
});

// Initialize
renderHistory();
displayOutput("cpp");