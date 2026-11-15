#include <iostream>
#include <string>
#include <vector>
#include <tuple>
#include <unordered_map>
#include <unordered_set>
#include <algorithm>
#include <numeric>
#include <cmath>
#include <cctype>
#include <sstream>
#include <stdexcept>
#include <functional>
#include <type_traits>

// ============================================================
// Python-Compatible C++17 Runtime Helpers
// ============================================================
namespace py_rt {

inline int py_mod(int a, int b) {
    if (b == 0) throw std::runtime_error("ZeroDivisionError: integer division or modulo by zero");
    int r = a % b;
    return (r != 0 && ((r < 0) != (b < 0))) ? r + b : r;
}

inline double py_mod(double a, double b) {
    if (b == 0.0) throw std::runtime_error("ZeroDivisionError: float modulo");
    double r = std::fmod(a, b);
    return (r != 0.0 && ((r < 0.0) != (b < 0.0))) ? r + b : r;
}

inline int py_floordiv(int a, int b) {
    if (b == 0) throw std::runtime_error("ZeroDivisionError: integer division or modulo by zero");
    int q = a / b;
    int r = a % b;
    return (r != 0 && ((r < 0) != (b < 0))) ? q - 1 : q;
}

inline double py_floordiv(double a, double b) {
    if (b == 0.0) throw std::runtime_error("ZeroDivisionError: float floor division by zero");
    return std::floor(a / b);
}

template <typename T>
inline T& py_index(std::vector<T>& vec, int idx) {
    int n = static_cast<int>(vec.size());
    int real_idx = idx < 0 ? n + idx : idx;
    if (real_idx < 0 || real_idx >= n) {
        throw std::out_of_range("IndexError: list index out of range");
    }
    return vec[real_idx];
}

template <typename T>
inline const T& py_index(const std::vector<T>& vec, int idx) {
    int n = static_cast<int>(vec.size());
    int real_idx = idx < 0 ? n + idx : idx;
    if (real_idx < 0 || real_idx >= n) {
        throw std::out_of_range("IndexError: list index out of range");
    }
    return vec[real_idx];
}

inline std::string py_index(const std::string& s, int idx) {
    int n = static_cast<int>(s.size());
    int real_idx = idx < 0 ? n + idx : idx;
    if (real_idx < 0 || real_idx >= n) {
        throw std::out_of_range("IndexError: string index out of range");
    }
    return std::string(1, s[real_idx]);
}

template <typename T>
inline std::vector<T> py_slice(const std::vector<T>& vec, int start, int stop, int step, bool has_start, bool has_stop) {
    if (step == 0) throw std::invalid_argument("ValueError: slice step cannot be zero");
    int n = static_cast<int>(vec.size());
    int s = has_start ? (start < 0 ? std::max(0, n + start) : std::min(n, start)) : (step > 0 ? 0 : n - 1);
    int e = has_stop ? (stop < 0 ? std::max(-1, n + stop) : std::min(n, stop)) : (step > 0 ? n : -1);
    std::vector<T> out;
    if (step > 0) {
        for (int i = s; i < e; i += step) out.push_back(vec[i]);
    } else {
        for (int i = s; i > e; i += step) out.push_back(vec[i]);
    }
    return out;
}

inline std::string py_slice(const std::string& str, int start, int stop, int step, bool has_start, bool has_stop) {
    if (step == 0) throw std::invalid_argument("ValueError: slice step cannot be zero");
    int n = static_cast<int>(str.size());
    int s = has_start ? (start < 0 ? std::max(0, n + start) : std::min(n, start)) : (step > 0 ? 0 : n - 1);
    int e = has_stop ? (stop < 0 ? std::max(-1, n + stop) : std::min(n, stop)) : (step > 0 ? n : -1);
    std::string out;
    if (step > 0) {
        for (int i = s; i < e; i += step) out.push_back(str[i]);
    } else {
        for (int i = s; i > e; i += step) out.push_back(str[i]);
    }
    return out;
}

inline std::string str_repeat(const std::string& s, int times) {
    std::string out;
    if (times <= 0) return out;
    out.reserve(s.size() * times);
    for (int i = 0; i < times; ++i) out += s;
    return out;
}

inline std::string str_upper(std::string s) {
    std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) { return std::toupper(c); });
    return s;
}

inline std::string str_lower(std::string s) {
    std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) { return std::tolower(c); });
    return s;
}

inline std::string str_strip(const std::string& s) {
    size_t start = s.find_first_not_of(" \t\n\r");
    if (start == std::string::npos) return "";
    size_t end = s.find_last_not_of(" \t\n\r");
    return s.substr(start, end - start + 1);
}

inline std::string str_replace(std::string s, const std::string& from, const std::string& to) {
    if (from.empty()) return s;
    size_t pos = 0;
    while ((pos = s.find(from, pos)) != std::string::npos) {
        s.replace(pos, from.length(), to);
        pos += to.length();
    }
    return s;
}

inline std::vector<std::string> str_split(const std::string& s, const std::string& sep = "") {
    std::vector<std::string> res;
    if (sep.empty()) {
        std::istringstream iss(s);
        std::string token;
        while (iss >> token) res.push_back(token);
        return res;
    }
    size_t start = 0, end;
    while ((end = s.find(sep, start)) != std::string::npos) {
        res.push_back(s.substr(start, end - start));
        start = end + sep.length();
    }
    res.push_back(s.substr(start));
    return res;
}

inline std::string str_join(const std::string& sep, const std::vector<std::string>& items) {
    std::string out;
    for (size_t i = 0; i < items.size(); ++i) {
        if (i > 0) out += sep;
        out += items[i];
    }
    return out;
}

inline std::string py_input(const std::string& prompt = "") {
    if (!prompt.empty()) {
        std::cout << prompt;
        std::cout.flush();
    }
    std::string line;
    std::getline(std::cin, line);
    return line;
}

template <typename T>
inline bool py_in(const T& item, const std::vector<T>& vec) {
    return std::find(vec.begin(), vec.end(), item) != vec.end();
}

template <typename T>
inline bool py_in(const T& item, const std::unordered_set<T>& st) {
    return st.find(item) != st.end();
}

template <typename K, typename V>
inline bool py_in(const K& key, const std::unordered_map<K, V>& mp) {
    return mp.find(key) != mp.end();
}

inline bool py_in(const std::string& sub, const std::string& s) {
    return s.find(sub) != std::string::npos;
}

template <typename T>
inline std::vector<T> py_sorted(std::vector<T> vec, bool reverse = false) {
    if (reverse) {
        std::sort(vec.begin(), vec.end(), std::greater<T>());
    } else {
        std::sort(vec.begin(), vec.end());
    }
    return vec;
}

template <typename T>
inline std::vector<T> py_reversed(std::vector<T> vec) {
    std::reverse(vec.begin(), vec.end());
    return vec;
}

template <typename T>
inline T py_sum(const std::vector<T>& vec) {
    return std::accumulate(vec.begin(), vec.end(), T{});
}

template <typename T>
inline std::vector<std::tuple<int, T>> py_enumerate(const std::vector<T>& vec, int start = 0) {
    std::vector<std::tuple<int, T>> out;
    out.reserve(vec.size());
    for (size_t i = 0; i < vec.size(); ++i) {
        out.emplace_back(start + static_cast<int>(i), vec[i]);
    }
    return out;
}

template <typename A, typename B>
inline std::vector<std::tuple<A, B>> py_zip(const std::vector<A>& a, const std::vector<B>& b) {
    size_t n = std::min(a.size(), b.size());
    std::vector<std::tuple<A, B>> out;
    out.reserve(n);
    for (size_t i = 0; i < n; ++i) {
        out.emplace_back(a[i], b[i]);
    }
    return out;
}

inline std::string to_py_str(const std::string& v) { return v; }
inline std::string to_py_str(const char* v) { return std::string(v); }
inline std::string to_py_str(bool v) { return v ? "True" : "False"; }
inline std::string to_py_str(int v) { return std::to_string(v); }
inline std::string to_py_str(long long v) { return std::to_string(v); }
inline std::string to_py_str(double v) {
    std::ostringstream oss;
    oss << v;
    std::string s = oss.str();
    if (s.find('.') == std::string::npos && s.find('e') == std::string::npos) {
        s += ".0";
    }
    return s;
}

template <typename T>
inline std::ostream& operator<<(std::ostream& os, const std::vector<T>& vec) {
    os << "[";
    for (size_t i = 0; i < vec.size(); ++i) {
        if (i > 0) os << ", ";
        if constexpr (std::is_same_v<T, std::string>) {
            os << "'" << vec[i] << "'";
        } else {
            os << vec[i];
        }
    }
    os << "]";
    return os;
}

template <typename K, typename V>
inline std::ostream& operator<<(std::ostream& os, const std::unordered_map<K, V>& mp) {
    os << "{";
    bool first = true;
    for (const auto& [k, v] : mp) {
        if (!first) os << ", ";
        first = false;
        if constexpr (std::is_same_v<K, std::string>) os << "'" << k << "'";
        else os << k;
        os << ": ";
        if constexpr (std::is_same_v<V, std::string>) os << "'" << v << "'";
        else os << v;
    }
    os << "}";
    return os;
}

} // namespace py_rt

using py_rt::operator<<;

// Function Prototypes
int factorial(int n);
int add(int a, int b = 5);

int factorial(int n) {
    if ((n <= 1)) {
        return 1;
    }
    return (n * factorial((n - 1)));
}

int add(int a, int b) {
    return (a + b);
}

int main() {
    std::cout << std::boolalpha;
    std::cout << std::string("5! =") << " " << factorial(5) << "\n";
    std::cout << std::string("add(10) =") << " " << add(10) << "\n";
    return 0;
}