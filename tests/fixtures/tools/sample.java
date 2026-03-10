import java.util.List;
import java.util.ArrayList;

public class Calculator {
    private int result;

    public Calculator() {
        this.result = 0;
    }

    public int add(int a, int b) {
        return a + b;
    }

    public int subtract(int a, int b) {
        return a - b;
    }

    private int multiply(int a, int b) {
        return a * b;
    }
}

interface Computable {
    int compute(int input);
}

enum Operation {
    ADD,
    SUBTRACT,
    MULTIPLY
}
