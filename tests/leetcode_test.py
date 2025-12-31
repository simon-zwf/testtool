# ==================================================
# !/usr/bin/env python
# @Author: simon.zhang
# @Date: 2025/11/26 09:47
# @FileName: leetcode_test.py
# @Email: wangfu_zhang@ggec.com.cn
# ==================================================
from typing import List

# Definition for singly-linked list:
class ListNode:
    def __init__(self, val=0, next=None):
        self.val = val
        self.next = next

class Solution:
    def twosum(self, nums: List[int], target:int)-> List[int]:
        hashmap = {}  # 空字典，用于存储数组元素值和对于的下标
        for i,num in enumerate(nums):  # for i in range（len(nums): num= nums[i]
            complement = target - num
            if complement in hashmap:
                print(f"找到目标！两数为: nums[{hashmap[complement]}]={complement} 和 nums[{i}]={num}")
                return [hashmap[complement],i]
            hashmap[num] =i
            #print(nums[i])
        return []

    def addTwoNumbers(self, l1: ListNode, l2:ListNode)-> ListNode:
        dummy = ListNode(0)
        curr = dummy
        carry = 0

        while l1 or l2 or carry:
            val1 = l1.val if l1 else 0
            val2 = l2.val if l2 else 0

            total = val1 + val2 + carry
            carry = total // 10
            curr.next = ListNode(total % 10)
            curr = curr.next

            if l1: l1 = l1.next
            if l2: l2 = l2.next

        return dummy.next

def  multiplication_table():
    for i in  range(1,10):
        for j in range(i, 10):
            print(f"{i}*{j}={i*j}", end='\t')
        print()


def testsum(numbers):
    c = sum(numbers)
    print(f"{c}")

def maxmin(a,b):
    cmax = max(a,b)
    cmin = min(a,b)
    print(f"max={cmax}, min={cmin}")

def testtype(age):
    if isinstance(age, int) and age>0:
        print(f"input the age is init")
    elif isinstance(age, (int,float)) and age >=0:
        print(f"non-negative number ")
    else:
        print(f"can't input {age}({type(age).__name__})")

def createLinkedList(arr):
    if not arr:
        return None
    head = ListNode(arr[0])
    cur = head
    for i in range(1, len(arr)):
        cur.next = ListNode(arr[i])
        cur = cur.next
    return head

def printLinkedList(head):
    res = []
    while head:
        res.append(head.val)
        head = head.next
    print(res)
if __name__ == "__main__":
    solution = Solution()
    print(solution.twosum([2,3,6,7],8))
    testsum([2, 6, 29])
    maxmin(2,4)
    testtype(50)
    testtype(-1)
    l1 = createLinkedList([2, 4, 3])
    l2 = createLinkedList([5, 6, 4])
    result = solution.addTwoNumbers(l1, l2)
    printLinkedList(result)
    multiplication_table()


