use std::collections::HashMap;

pub const MAX_SIZE: usize = 1024;

pub fn compute(x: i32, y: i32) -> i32 {
    x + y
}

fn helper(s: &str) -> String {
    s.to_uppercase()
}

pub struct Config {
    pub name: String,
    pub value: i32,
}

impl Config {
    pub fn new(name: &str, value: i32) -> Self {
        Config {
            name: name.to_string(),
            value,
        }
    }
}

pub enum Status {
    Active,
    Inactive,
}

pub trait Processor {
    fn process(&self, input: &str) -> String;
}
